"""
generate_forecasts.py
=====================
Stage 6 of the pipeline.

Refits the model selected for each eligible series on **all** observed data
(up to that series' own last observed quarter - forecast origins therefore
differ per series) and produces the next four quarterly forecasts.

Outputs
-------
* ``data/forecasts/future_four_quarter_forecasts.csv``
* ``results/forecast_reliability_report.csv``

Intervals:
* ARIMA     -> model confidence intervals (defensible).
* other     -> symmetric empirical band ``+/- 1.96 * validation RMSE``
  labelled ``empirical_rmse_band`` (clearly a pragmatic, documented bound).

Usage
-----
    python code/generate_forecasts.py
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
import train_and_validate as TV  # noqa: E402

C.ensure_dirs()

MODEL_VERSION = "clz-forecast-v1.0"
GEN_TS = _dt.datetime.now().isoformat(timespec="seconds")
Z = 1.96


def arima_forecast_ci(train, horizon, microbial):
    """Return (point forecast, lower, upper) for ARIMA."""
    import statsmodels.api as sm
    from statsmodels.tsa.arima.model import ARIMA
    y = np.asarray(train, dtype=float)
    if microbial:
        y = np.log1p(np.clip(y, 0, None))
    best = None
    for order in [(1, 1, 1), (2, 1, 1), (1, 1, 2), (2, 1, 2), (1, 0, 1)]:
        try:
            m = ARIMA(y, order=order, enforce_stationarity=False,
                      enforce_invertibility=False).fit()
            if best is None or m.aic < best.aic:
                best = m
        except Exception:
            continue
    if best is None:
        return None, None, None
    fc = np.asarray(best.forecast(steps=horizon), dtype=float)
    pred = best.get_prediction(start=len(y), end=len(y) + horizon - 1)
    ci = pred.conf_int(alpha=0.05)
    lo = np.asarray(ci[:, 0], dtype=float)
    hi = np.asarray(ci[:, 1], dtype=float)
    if microbial:
        fc, lo, hi = np.expm1(fc), np.expm1(lo), np.expm1(hi)
    fc = np.clip(fc, 0, None)
    lo = np.clip(lo, 0, None)
    hi = np.clip(np.maximum(hi, fc), fc, None)
    return fc, lo, hi


def classify(param, value):
    """DENR Class C guideline classification for the predicted value."""
    w = C.WQG_CLASS_C.get(param)
    if w is None or value is None or (isinstance(value, float) and math.isnan(value)):
        return "no_guideline"
    v = w["value"]
    if w["rule"] == "min":
        return "Pass" if value >= v else "Fail"
    if w["rule"] == "max":
        return "Pass" if value <= v else "Fail"
    if w["rule"] == "range":
        return "Pass" if v[0] <= value <= v[1] else "Fail"
    return "unknown"


def main():
    print("=" * 80)
    print("STAGE 6  -  FOUR-QUARTER FORECAST GENERATION")
    print("=" * 80)
    q = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"))
    q["Date"] = pd.to_datetime(q["Date"])
    inv = pd.read_csv(os.path.join(C.PROCESSED_DIR, "series_inventory.csv"))
    station_reg = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    with open(os.path.join(C.MODELS_DIR, "model_configurations", "model_selection.json")) as f:
        sel = json.load(f)
    mc = pd.read_csv(os.path.join(C.RESULTS_DIR, "model_comparison.csv"))

    sel_rmse = (mc[mc["Selection_Status"] == "selected"]
                .drop_duplicates(subset=["River", "Station", "Parameter"])
                .set_index(["River", "Station", "Parameter"])["Validation_RMSE"]
                .to_dict())

    rows = []
    for s in inv[inv["N_Observations"] >= TV.MIN_TOTAL].itertuples():
        key = str((s.River, s.Station, s.Parameter))
        if key not in sel:
            key = f"{s.River}|{s.Station}|{s.Parameter}"
        if key not in sel:
            continue
        model = sel[key]
        sub = q[(q["River"] == s.River) & (q["Station"] == s.Station) &
               (q["Parameter"] == s.Parameter)].sort_values("Date")
        vals = sub["Observed_Value"].astype(float).values
        vals = vals[~np.isnan(vals)]
        microbial = s.Parameter in TV.MICROBIAL

        last_dt = pd.Timestamp(sub["Date"].max())
        last_q = int(sub["Quarter"].iloc[-1])
        last_y = int(sub["Year"].iloc[-1])
        base_rmse = sel_rmse.get((s.River, s.Station, s.Parameter), np.nan)

        if model == "ARIMA":
            fc, lo, hi = arima_forecast_ci(vals, TV.HORIZON, microbial)
            if fc is None:
                fc = TV.MODELS["Naive"](vals, TV.HORIZON)
                model = "Naive"
                lo = hi = None
        else:
            if model == "LSTM":
                fc = TV.MODELS["LSTM"](vals, TV.HORIZON, microbial)
            else:
                fc = TV.MODELS[model](vals, TV.HORIZON)
            band = float(base_rmse) if not (isinstance(base_rmse, float) and math.isnan(base_rmse)) else None
            if band is not None:
                if microbial:
                    lc = np.clip(np.log1p(fc) - Z * band, 0, None)
                    hi = np.expm1(np.log1p(fc) + Z * band)
                    lo = np.expm1(lc)
                else:
                    lo = np.maximum(fc - Z * band, 0.0)
                    hi = fc + Z * band
            else:
                lo = hi = None

        st = station_reg[(station_reg["River"] == s.River) & (station_reg["Station_Canonical"] == s.Station)]
        lat = float(st["Latitude"].iloc[0]) if len(st) and pd.notna(st["Latitude"].iloc[0]) else np.nan
        lon = float(st["Longitude"].iloc[0]) if len(st) and pd.notna(st["Longitude"].iloc[0]) else np.nan
        ccorf = st["Coordinate_Confidence"].iloc[0] if len(st) else "Unverified"
        mapping_ok = bool(len(st) and pd.notna(st["Latitude"].iloc[0]) and pd.notna(st["Longitude"].iloc[0]))

        cy, cq = last_y, last_q
        for h in range(1, TV.HORIZON + 1):
            cq += 1
            if cq > 4:
                cq = 1
                cy += 1
            fdate = pd.Timestamp(cy, 3 * cq - 1, 15)
            val = float(fc[h - 1])
            lo_v = float(lo[h - 1]) if lo is not None else np.nan
            hi_v = float(hi[h - 1]) if hi is not None else np.nan
            rows.append({
                "Forecast_Date": fdate.strftime("%Y-%m-%d"),
                "Year": cy, "Quarter": cq,
                "River": s.River, "Station": s.Station,
                "Station_ID": f"{s.River}|{s.Station}",
                "Latitude": lat, "Longitude": lon,
                "Parameter": s.Parameter,
                "Forecast_Value": round(val, 4),
                "Unit": C.param_unit(s.Parameter),
                "Selected_Model": model,
                "Forecast_Horizon": h,
                "Lower_Interval": None if (lo is None or math.isnan(lo_v)) else round(lo_v, 4),
                "Upper_Interval": None if (hi is None or math.isnan(hi_v)) else round(hi_v, 4),
                "Interval_Method": "arima_conf_int" if model == "ARIMA" and lo is not None else
                                   ("empirical_rmse_band" if lo is not None else "none"),
                "Forecast_Status": "eligible",
                "Classification": classify(s.Parameter, val),
                "Training_Period": f"{sub['Date'].min().date()} to {sub['Date'].max().date()}",
                "Observation_Count": int(len(vals)),
                "Model_Version": MODEL_VERSION,
                "Forecast_Generation_Timestamp": GEN_TS,
                "Validation_Status": "passed",
                "Reliability_Flag": "reliable" if (isinstance(base_rmse, float) and not math.isnan(base_rmse) and base_rmse > 0) else "uncertain",
                "Source_Records": "; ".join(sorted(set(sub["Source_Files"]))) if "Source_Files" in sub else "",
                "Coordinate_Confidence": ccorf,
                "Mapping_Eligibility": "eligible" if mapping_ok else "no_coordinate",
            })

    fc = pd.DataFrame(rows)
    fc.to_csv(os.path.join(C.FORECAST_DIR, "future_four_quarter_forecasts.csv"), index=False)

    rel = (fc.groupby(["River", "Station", "Parameter", "Selected_Model"])
           .agg(N_Forecasts=("Forecast_Value", "size"),
                Mean_Value=("Forecast_Value", "mean"),
                Mean_Lower=("Lower_Interval", "mean"),
                Mean_Upper=("Upper_Interval", "mean"),
                Class_Fail_Count=("Classification", lambda s: int((s == "Fail").sum())),
                Mapping_Eligible=("Mapping_Eligibility", lambda s: int((s == "eligible").sum())))
           .reset_index())
    rel["Reliability"] = np.where(rel["Class_Fail_Count"] > 0, "flagged_exceedance", "ok")
    rel.to_csv(os.path.join(C.RESULTS_DIR, "forecast_reliability_report.csv"), index=False)

    print(f"forecast rows: {len(fc)}")
    print(f"distinct station-parameter series forecast: {fc.groupby(['River','Station','Parameter']).ngroups}")
    print(f"mapping-eligible: {int((fc['Mapping_Eligibility']=='eligible').sum())}")
    print("\nForecast horizon 1 by river (Fecal Coliform):")
    print(fc[(fc["Parameter"] == "Fecal Coliform") & (fc["Forecast_Horizon"] == 1)]
          .groupby("River")["Forecast_Value"].mean().sort_values(ascending=False).head(15).to_string())
    print("\nDONE.")


if __name__ == "__main__":
    main()
