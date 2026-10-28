"""
train_and_validate.py
=====================
Stage 5 of the pipeline.

For every eligible river / station / parameter quarterly series the script
compares four forecasting models under a strictly chronological
expanding-window protocol:

* ``Naive``            - repeat the last observed quarter.
* ``SeasonalNaive``    - repeat the last annual (4-quarter) cycle.
* ``ARIMA``            - statsmodels ARIMA with automatic order search.
* ``LSTM``             - a compact single-series torch LSTM.

No observation is ever shuffled, and every model is evaluated on exactly the
same expanding-window origins.  Microbial counts (Fecal Coliform, Total
Coliform) are modelled on a ``log1p`` scale and back-transformed exactly once.

Outputs
-------
* ``results/model_comparison.csv``
* ``results/historical_backtest_predictions.csv``   (final held-out 4 quarters)
* ``models/model_configurations/model_selection.json``

Usage
-----
    python code/train_and_validate.py
"""

from __future__ import annotations

import os
import sys
import json
import math
import warnings
import datetime as _dt

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
try:
    from statsmodels.tools.sm_exceptions import ConvergenceWarning as _CW
    warnings.filterwarnings("ignore", category=_CW)
except Exception:  # pragma: no cover
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

torch.set_num_threads(max(1, os.cpu_count() // 2))
np.random.seed(42)
torch.manual_seed(42)

SEASONAL_PERIOD = 4          # quarters
HORIZON = 4                  # four-quarter forecast
MIN_TOTAL = 20               # need >=20 quarterly points to run the protocol
MIN_TRAIN = 16               # at least 16 points before the final test window
MAX_ORIGINS = 6              # expanding-window origins kept for selection
LSTM_SEQ = 8
LSTM_HIDDEN = 24
LSTM_EPOCHS = 35
LSTM_LR = 0.01

MICROBIAL = {"Fecal Coliform", "Total Coliform"}


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
def naive_forecast(train, horizon):
    return np.full(horizon, float(train[-1]))


def seasonal_naive_forecast(train, horizon, m=SEASONAL_PERIOD):
    if len(train) < m:
        return naive_forecast(train, horizon)
    cycle = np.asarray(train[-m:], dtype=float)
    reps = int(math.ceil(horizon / m))
    return np.tile(cycle, reps)[:horizon]


def _fit_arima(series, order_list, microbial):
    import statsmodels.api as sm
    from statsmodels.tsa.arima.model import ARIMA
    y = np.asarray(series, dtype=float)
    if microbial:
        y = np.log1p(np.clip(y, 0, None))
    best = None
    for order in order_list:
        try:
            m = ARIMA(y, order=order, enforce_stationarity=False,
                      enforce_invertibility=False).fit()
            if best is None or m.aic < best.aic:
                best = m
        except Exception:
            continue
    return best


def arima_forecast(train, horizon, microbial):
    if len(train) < 5:
        return naive_forecast(train, horizon)
    try:
        model = _fit_arima(train, [(1, 1, 1), (2, 1, 1), (1, 1, 2), (2, 1, 2), (1, 0, 1)], microbial)
        if model is None:
            return naive_forecast(train, horizon)
        fc = np.asarray(model.forecast(steps=horizon), dtype=float)
        if microbial:
            fc = np.expm1(fc)
        return np.clip(fc, 0, None)
    except Exception:
        return naive_forecast(train, horizon)


class _LSTM(nn.Module):
    def __init__(self, d=1, h=LSTM_HIDDEN):
        super().__init__()
        self.lstm = nn.LSTM(d, h, num_layers=1, batch_first=True)
        self.fc = nn.Linear(h, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


def _to_sequences(data, seq):
    xs, ys = [], []
    for i in range(len(data) - seq):
        xs.append(data[i:i + seq])
        ys.append(data[i + seq])
    if not xs:
        return None, None
    return np.array(xs, dtype=np.float32).reshape(-1, seq, 1), np.array(ys, dtype=np.float32).reshape(-1, 1)


def lstm_forecast(train, horizon, microbial):
    y = np.asarray(train, dtype=float)
    if microbial:
        y = np.log1p(np.clip(y, 0, None))
    if len(y) < LSTM_SEQ + 2:
        return naive_forecast(train, horizon)
    mu, sd = float(y.mean()), float(y.std()) + 1e-6
    z = (y - mu) / sd
    X, Y = _to_sequences(z, LSTM_SEQ)
    if X is None:
        return naive_forecast(train, horizon)
    Xt = torch.tensor(X)
    Yt = torch.tensor(Y)
    model = _LSTM()
    opt = torch.optim.Adam(model.parameters(), lr=LSTM_LR)
    lossf = nn.MSELoss()
    model.train()
    for _ in range(LSTM_EPOCHS):
        opt.zero_grad()
        pred = model(Xt)
        loss = lossf(pred, Yt)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
    model.eval()
    window = list(z[-LSTM_SEQ:])
    fc = []
    with torch.no_grad():
        for _ in range(horizon):
            x = torch.tensor(np.array(window, dtype=np.float32).reshape(1, LSTM_SEQ, 1))
            p = model(x).item()
            fc.append(p)
            window = window[1:] + [p]
    fc = np.array(fc) * sd + mu
    if microbial:
        fc = np.expm1(fc)
    return np.clip(fc, 0, None)


MODELS = {
    "Naive": naive_forecast,
    "SeasonalNaive": seasonal_naive_forecast,
    "ARIMA": arima_forecast,
    "LSTM": lstm_forecast,
}


def metrics(actual, pred):
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    err = pred - actual
    mae = float(np.mean(np.abs(err)))
    mse = float(np.mean(err ** 2))
    rmse = float(math.sqrt(mse))
    return mae, mse, rmse


def mase(train, actual, pred, m=SEASONAL_PERIOD):
    train = np.asarray(train, dtype=float)
    if len(train) > m:
        denom = np.mean(np.abs(train[m:] - train[:-m]))
    else:
        denom = np.mean(np.abs(np.diff(train)))
    if denom == 0:
        return float("nan")
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(actual))) / denom)


def expanding_origins(n):
    """Chronological origins (index of last training point) for validation."""
    # need at least MIN_TRAIN before the first origin, step SEASONAL_PERIOD
    starts = [MIN_TRAIN]
    o = MIN_TRAIN + SEASONAL_PERIOD
    while o + HORIZON <= n - HORIZON and len(starts) < MAX_ORIGINS:
        starts.append(o)
        o += SEASONAL_PERIOD
    return starts


def evaluate_series(vals, microbial):
    """Return per-model validation metrics + the selected model name."""
    n = len(vals)
    origins = expanding_origins(n)
    acc = {m: {"mae": [], "rmse": [], "mase": []} for m in MODELS}
    for o in origins:
        train = vals[:o]
        actual = vals[o:o + HORIZON]
        if len(actual) < HORIZON:
            continue
        for name, fn in MODELS.items():
            try:
                pred = fn(train, HORIZON, microbial) if name in ("ARIMA", "LSTM") else fn(train, HORIZON)
            except Exception:
                continue
            pred = np.asarray(pred, dtype=float)[:len(actual)]
            mae, mse, rmse = metrics(actual, pred)
            acc[name]["mae"].append(mae)
            acc[name]["rmse"].append(rmse)
            acc[name]["mase"].append(mase(train, actual, pred))
    rows = []
    for name in MODELS:
        if not acc[name]["rmse"]:
            continue
        rows.append({
            "Model": name,
            "Validation_MAE": float(np.mean(acc[name]["mae"])),
            "Validation_RMSE": float(np.mean(acc[name]["rmse"])),
            "Validation_MASE": float(np.mean(acc[name]["mase"])),
            "N_Origins": len(acc[name]["rmse"]),
        })
    if not rows:
        return None, None
    best = min(rows, key=lambda r: r["Validation_RMSE"])
    return rows, best["Model"]


def final_backtest(vals, model_name, microbial):
    """Out-of-sample predictions for the last HORIZON quarters."""
    n = len(vals)
    if n < MIN_TRAIN + HORIZON:
        return None, None
    train = vals[:n - HORIZON]
    actual = vals[n - HORIZON:]
    fn = MODELS[model_name]
    pred = fn(train, HORIZON, microbial) if model_name in ("ARIMA", "LSTM") else fn(train, HORIZON)
    pred = np.asarray(pred, dtype=float)[:len(actual)]
    mae, mse, rmse = metrics(actual, pred)
    return actual, pred, (mae, mse, rmse, mase(train, actual, pred))


def main():
    print("=" * 80)
    print("STAGE 5  -  CHRONOLOGICAL MODEL VALIDATION")
    print("=" * 80)
    q = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"))
    inv = pd.read_csv(os.path.join(C.PROCESSED_DIR, "series_inventory.csv"))

    elig = inv[(inv["N_Observations"] >= MIN_TOTAL)].copy()
    print(f"eligible series (>= {MIN_TOTAL} quarterly obs): {len(elig)}")

    model_rows = []
    backtest_rows = []
    sel_map = {}

    for _, s in elig.iterrows():
        key = (s["River"], s["Station"], s["Parameter"])
        sub = q[(q["River"] == s["River"]) & (q["Station"] == s["Station"]) &
               (q["Parameter"] == s["Parameter"])].sort_values("Date")
        vals = sub["Observed_Value"].astype(float).values
        microbial = s["Parameter"] in MICROBIAL
        if np.isnan(vals).any():
            vals = vals[~np.isnan(vals)]
        rows, best = evaluate_series(vals, microbial)
        if best is None:
            continue
        sel_map[str(key)] = best
        for r in rows:
            model_rows.append({
                "River": s["River"], "Station": s["Station"], "Parameter": s["Parameter"],
                "Model": r["Model"], "Validation_MAE": r["Validation_MAE"],
                "Validation_RMSE": r["Validation_RMSE"], "Validation_MASE": r["Validation_MASE"],
                "N_Origins": r["N_Origins"],
                "Selection_Status": "selected" if r["Model"] == best else "not_selected",
            })
        bt = final_backtest(vals, best, microbial)
        if bt[0] is not None:
            actual, pred, (mae, mse, rmse, ms) = bt
            n = len(vals)
            base = sub["Date"].values[-HORIZON:]
            for i in range(HORIZON):
                backtest_rows.append({
                    "River": s["River"], "Station": s["Station"], "Parameter": s["Parameter"],
                    "Date": pd.Timestamp(base[i]).strftime("%Y-%m-%d"),
                    "Quarter": int(sub["Quarter"].values[-HORIZON + i]),
                    "Actual_Value": float(actual[i]),
                    "Predicted_Value": float(pred[i]),
                    "Selected_Model": best,
                    "Absolute_Error": float(abs(pred[i] - actual[i])),
                })
            model_rows.append({
                "River": s["River"], "Station": s["Station"], "Parameter": s["Parameter"],
                "Model": best, "Validation_MAE": mae, "Validation_RMSE": rmse,
                "Validation_MASE": ms, "N_Origins": len(expanding_origins(n)),
                "Selection_Status": "selected",
            })
        if len(model_rows) % 500 == 0:
            print(f"  ... {len(model_rows)} model rows")

    mc = pd.DataFrame(model_rows)
    mc.to_csv(os.path.join(C.RESULTS_DIR, "model_comparison.csv"), index=False)
    bt = pd.DataFrame(backtest_rows)
    bt.to_csv(os.path.join(C.RESULTS_DIR, "historical_backtest_predictions.csv"), index=False)
    with open(os.path.join(C.MODELS_DIR, "model_configurations", "model_selection.json"), "w") as f:
        json.dump(sel_map, f, indent=1)

    print(f"\nModel comparison rows : {len(mc)}")
    print(f"Backtest rows         : {len(bt)}")
    print("\nSelected models (top):")
    print(mc[mc["Selection_Status"] == "selected"]["Model"].value_counts().to_string())
    print("\nAverage validation RMSE by model:")
    print(mc.groupby("Model")["Validation_RMSE"].mean().round(4).to_string())
    print("\nDONE.")


if __name__ == "__main__":
    main()
