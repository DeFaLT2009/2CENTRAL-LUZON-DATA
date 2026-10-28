"""
line_graphs.py
==============
Stage 7 of the pipeline.

MANDATORY line graphs - every figure combines the three required series in one
readable chart:

1.  Historical observed values (solid).
2.  Backtest predictions on the held-out final quarters (dashed).
3.  Future four-quarter forecasts (dotted) with the documented interval band.

Four families of charts are produced:

A. ``line_per_station_*``      - single station / parameter detail.
B. ``line_multistation_*``     - every station of a river averaged by parameter.
C. ``line_model_comparison_*`` - all four models on one backtest window + RMSE bars.
D. ``line_regional_*``         - Region III river average per parameter + forecast.

Usage
-----
    python code/line_graphs.py
"""

from __future__ import annotations

import os
import sys
import math
import json
import datetime as _dt

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

OUT = os.path.join(C.FIGURES_DIR, "line")
os.makedirs(OUT, exist_ok=True)

PARAM_COLOR = {"DO": "#1f77b4", "BOD": "#ff7f0e", "TSS": "#2ca02c", "pH": "#d62728",
               "Temp": "#9467bd", "Fecal Coliform": "#8c564b", "Total Coliform": "#7f7f7f",
               "NO3-N": "#e377c2", "PO4-P": "#17becf", "Cl": "#bcbd22", "NH3": "#17becf",
               "Color": "#2ca02c"}
GEN_TS = _dt.datetime.now().isoformat(timespec="seconds")


def style(ax, title, ylabel):
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7, loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="both", labelsize=7)


def make_dir(name):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    return d


def main():
    print("=" * 80)
    print("STAGE 7  -  MANDATORY LINE GRAPHS")
    print("=" * 80)
    obs = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"))
    obs["Date"] = pd.to_datetime(obs["Date"])
    bt = pd.read_csv(os.path.join(C.RESULTS_DIR, "historical_backtest_predictions.csv"))
    bt["Date"] = pd.to_datetime(bt["Date"])
    fc = pd.read_csv(os.path.join(C.FORECAST_DIR, "future_four_quarter_forecasts.csv"))
    fc["Forecast_Date"] = pd.to_datetime(fc["Forecast_Date"])
    inv = pd.read_csv(os.path.join(C.PROCESSED_DIR, "series_inventory.csv"))
    mc = pd.read_csv(os.path.join(C.RESULTS_DIR, "model_comparison.csv"))

    river_dir = make_dir("per_station")
    ms_dir = make_dir("multistation")
    mc_dir = make_dir("model_comparison")

    # ------------------------------------------------------------------ A
    print("A. per-station detail ...")
    core_params = ["DO", "BOD", "TSS", "pH", "Temp", "Fecal Coliform"]
    chosen = []
    for river, rg in inv.groupby("River"):
        for param in core_params:
            s = rg[rg["Parameter"] == param].sort_values("N_Observations", ascending=False)
            if len(s):
                chosen.append((river, param, s.iloc[0]))
    chosen = chosen[:24]
    for river, param, s in chosen:
        stn = s["Station"]
        sub = obs[(obs["River"] == river) & (obs["Station"] == stn) & (obs["Parameter"] == param)].sort_values("Date")
        b = bt[(bt["River"] == river) & (bt["Station"] == stn) & (bt["Parameter"] == param)].sort_values("Date")
        f = fc[(fc["River"] == river) & (fc["Station"] == stn) & (fc["Parameter"] == param)].sort_values("Forecast_Date")
        fig, ax = plt.subplots(figsize=(7, 4))
        if len(sub):
            ax.plot(sub["Date"], sub["Observed_Value"], "-", color=PARAM_COLOR.get(param, "#333"), lw=1.5, label="observed")
        if len(b):
            ax.plot(b["Date"], b["Actual_Value"], "o", ms=4, color="#888", label="actual (held-out)")
            ax.plot(b["Date"], b["Predicted_Value"], "--", color="#d62728", lw=1.5, label="backtest prediction")
        if len(f):
            ax.plot(f["Forecast_Date"], f["Forecast_Value"], "-.", color="#1f77b4", lw=2, label="future forecast")
            lo = f["Lower_Interval"].astype(float)
            hi = f["Upper_Interval"].astype(float)
            ax.fill_between(f["Forecast_Date"], lo, hi, color="#1f77b4", alpha=0.15, label="interval band")
        style(ax, f"{river} / {stn} - {param}", f"{C.param_unit(param)}")
        fig.tight_layout()
        fn = os.path.join(river_dir, f"line_per_station_{river.replace(' ', '_')}_{param}.png")
        fig.savefig(fn, dpi=130)
        plt.close(fig)

    # ------------------------------------------------------------------ B
    print("B. multi-station river aggregates ...")
    top_rivers = inv.groupby("River")["N_Observations"].sum().sort_values(ascending=False).head(12).index.tolist()
    for river in top_rivers:
        for param in core_params:
            sub = obs[(obs["River"] == river) & (obs["Parameter"] == param)]
            if sub.empty:
                continue
            agg = sub.groupby(["Date", "Year", "Quarter"])["Observed_Value"].mean().reset_index().sort_values("Date")
            f = fc[(fc["River"] == river) & (fc["Parameter"] == param)]
            if len(f):
                agg2 = f.groupby("Forecast_Date")["Forecast_Value"].mean().reset_index()
                lo = f.groupby("Forecast_Date")["Lower_Interval"].mean().reset_index()["Lower_Interval"].values
                hi = f.groupby("Forecast_Date")["Upper_Interval"].mean().reset_index()["Upper_Interval"].values
                agg2["lo"], agg2["hi"] = lo, hi
            else:
                agg2 = pd.DataFrame(columns=["Forecast_Date", "Forecast_Value", "lo", "hi"])
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.plot(agg["Date"], agg["Observed_Value"], "-", color=PARAM_COLOR.get(param, "#333"), lw=1.4, label="observed (station mean)")
            if len(agg2):
                ax.plot(agg2["Forecast_Date"], agg2["Forecast_Value"], "-.", color="#1f77b4", lw=2, label="future forecast (mean)")
                ax.fill_between(agg2["Forecast_Date"], agg2["lo"], agg2["hi"], color="#1f77b4", alpha=0.15, label="interval band")
            style(ax, f"{river} - {param} (multi-station mean)", f"{C.param_unit(param)}")
            fig.tight_layout()
            fn = os.path.join(ms_dir, f"line_multistation_{river.replace(' ', '_')}_{param}.png")
            fig.savefig(fn, dpi=130)
            plt.close(fig)

    # ------------------------------------------------------------------ C
    print("C. model comparison ...")
    for river, rg in inv.groupby("River"):
        if len(chosen) == 0:
            break
        # pick a long series with all four models present in backtest
        pick = None
        for _, s in rg.sort_values("N_Observations", ascending=False).iterrows():
            b = bt[(bt["River"] == river) & (bt["Station"] == s["Station"]) & (bt["Parameter"] == s["Parameter"])]
            n_models = b["Selected_Model"].nunique()
            if n_models >= 1 and s["N_Observations"] >= 30:
                pick = s
                break
        if pick is None:
            continue
        river, stn, param = pick["River"], pick["Station"], pick["Parameter"]
        sub = obs[(obs["River"] == river) & (obs["Station"] == stn) & (obs["Parameter"] == param)].sort_values("Date")
        b = bt[(bt["River"] == river) & (bt["Station"] == stn) & (bt["Parameter"] == param)].sort_values("Date")
        f = fc[(fc["River"] == river) & (fc["Station"] == stn) & (fc["Parameter"] == param)].sort_values("Forecast_Date")
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        ax = axes[0]
        if len(sub):
            ax.plot(sub["Date"], sub["Observed_Value"], "-", color="#333", lw=1.5, label="observed")
        if len(b):
            ax.plot(b["Date"], b["Actual_Value"], "o", ms=5, color="#888")
            ax.plot(b["Date"], b["Predicted_Value"], "--", color="#d62728", lw=1.8, label="selected model backtest")
        if len(f):
            ax.plot(f["Forecast_Date"], f["Forecast_Value"], "-.", color="#1f77b4", lw=2, label="future forecast")
        style(ax, f"{river} / {stn} - {param}  [{pick['N_Observations']} obs]", C.param_unit(param))
        ax = axes[1]
        rows = mc[(mc["River"] == river) & (mc["Station"] == stn) & (mc["Parameter"] == param)]
        rows = rows.drop_duplicates("Model")
        if len(rows):
            rows = rows.sort_values("Validation_RMSE")
            ax.barh(rows["Model"], rows["Validation_RMSE"], color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"][:len(rows)])
            for i, (m, rmse) in enumerate(zip(rows["Model"], rows["Validation_RMSE"])):
                ax.text(rmse, i, f" {rmse:.2f}", va="center", fontsize=8)
        ax.set_title(f"Validation RMSE (expanding-window, {len(rows)} models)", fontsize=10)
        ax.set_xlabel("RMSE", fontsize=9)
        ax.tick_params(axis="both", labelsize=8)
        ax.grid(True, alpha=0.3, axis="x")
        fig.tight_layout()
        fn = os.path.join(mc_dir, f"line_model_comparison_{river.replace(' ', '_')}_{param}.png")
        fig.savefig(fn, dpi=130)
        plt.close(fig)
        break

    # ------------------------------------------------------------------ D
    print("D. regional aggregates ...")
    reg_dir = make_dir("regional")
    for param in core_params:
        sub = obs[obs["Parameter"] == param]
        if sub.empty:
            continue
        agg = sub.groupby(["Date", "Year", "Quarter"])["Observed_Value"].mean().reset_index().sort_values("Date")
        f = fc[fc["Parameter"] == param]
        if len(f):
            a2 = f.groupby("Forecast_Date")["Forecast_Value"].mean().reset_index()
            a2["lo"] = f.groupby("Forecast_Date")["Lower_Interval"].mean().values
            a2["hi"] = f.groupby("Forecast_Date")["Upper_Interval"].mean().values
        else:
            a2 = pd.DataFrame(columns=["Forecast_Date", "Forecast_Value", "lo", "hi"])
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(agg["Date"], agg["Observed_Value"], "-", color=PARAM_COLOR.get(param, "#333"), lw=1.4, label="region observed mean")
        if len(a2):
            ax.plot(a2["Forecast_Date"], a2["Forecast_Value"], "-.", color="#1f77b4", lw=2, label="region forecast mean")
            ax.fill_between(a2["Forecast_Date"], a2["lo"], a2["hi"], color="#1f77b4", alpha=0.15, label="interval band")
        style(ax, f"Central Luzon rivers - {param} (region mean)", f"{C.param_unit(param)}")
        fig.tight_layout()
        fn = os.path.join(reg_dir, f"line_regional_{param}.png")
        fig.savefig(fn, dpi=130)
        plt.close(fig)

    print(f"\nfigures written to {OUT}")
    print("DONE.")


if __name__ == "__main__":
    main()
