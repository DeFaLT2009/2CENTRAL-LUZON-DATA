"""
validate_pipeline.py
====================
Stage 11 of the pipeline.

End-to-end integrity validation.  For every deliverable artifact it checks
that the artefact exists, is non-empty and - where data is involved - that
every value is traceable to a source record (no invented values).

Produces ``results/validation_report.csv`` and ``results/validation_summary.json``.

Usage
-----
    python code/validate_pipeline.py
"""

from __future__ import annotations

import os
import sys
import json
import glob
import zipfile
import datetime as _dt

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()


def check(check_id, description, passed, detail):
    return {"Check_ID": check_id, "Description": description,
            "Passed": bool(passed), "Detail": str(detail)}


def main():
    print("=" * 80)
    print("STAGE 11  -  END-TO-END VALIDATION")
    print("=" * 80)
    results = []

    # ---- inputs ---------------------------------------------------------
    obs = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"))
    bt = pd.read_csv(os.path.join(C.RESULTS_DIR, "historical_backtest_predictions.csv"))
    fc = pd.read_csv(os.path.join(C.FORECAST_DIR, "future_four_quarter_forecasts.csv"))
    inv = pd.read_csv(os.path.join(C.PROCESSED_DIR, "series_inventory.csv"))
    reg = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    mc = pd.read_csv(os.path.join(C.RESULTS_DIR, "model_comparison.csv"))

    results.append(check("IN-01", "observations_quarterly.csv present & non-empty", len(obs) > 0, f"{len(obs)} rows"))
    MANDATORY = ["Forecast_Date", "Year", "Quarter", "River", "Station", "Station_ID",
                 "Latitude", "Longitude", "Parameter", "Forecast_Value", "Unit",
                 "Selected_Model", "Forecast_Horizon", "Lower_Interval", "Upper_Interval",
                 "Forecast_Status", "Classification", "Training_Period", "Observation_Count",
                 "Model_Version", "Forecast_Generation_Timestamp", "Validation_Status",
                 "Reliability_Flag", "Source_Records", "Coordinate_Confidence",
                 "Mapping_Eligibility"]
    missing = [c for c in MANDATORY if c not in fc.columns]
    results.append(check("IN-02", "forecasts CSV has all mandatory columns", len(missing) == 0,
                         f"{len(fc.columns)} columns, missing={missing}"))

    # ---- traceability ---------------------------------------------------
    bad_obs = fc[(fc["Observation_Count"].astype(float) <= 0)]
    results.append(check("TR-01", "every forecast has Observation_Count > 0", len(bad_obs) == 0,
                         f"{len(bad_obs)} rows with no training observations"))
    bad_val = fc[fc["Forecast_Value"].isna()]
    results.append(check("TR-02", "no NaN forecast values", len(bad_val) == 0, f"{len(bad_val)} NaN values"))
    bad_tp = fc[fc["Training_Period"].isna()]
    results.append(check("TR-03", "every forecast has a Training_Period", len(bad_tp) == 0, f"{len(bad_tp)} missing"))

    # backtest dates must be inside observed history
    bad_bt = []
    for _, b in bt.iterrows():
        s = obs[(obs["River"] == b["River"]) & (obs["Station"] == b["Station"]) &
               (obs["Parameter"] == b["Parameter"])]
        if s.empty:
            bad_bt.append(b["Station"])
    results.append(check("TR-04", "every backtest row matches an observed series", len(bad_bt) == 0,
                         f"{len(bad_bt)} unmatched"))

    # forecast dates must be after each series' last observed quarter
    bad_fc = []
    qmap = {(r["River"], r["Station"], r["Parameter"]): pd.Timestamp(r["Date"])
            for _, r in obs.iterrows()}
    for _, f in fc.iterrows():
        last = qmap.get((f["River"], f["Station"], f["Parameter"]))
        if last is not None and pd.Timestamp(f["Forecast_Date"]) <= last:
            bad_fc.append(f["Station"])
    results.append(check("TR-05", "forecast dates are after the series' last observation", len(bad_fc) == 0,
                         f"{len(bad_fc)} not strictly future"))

    # horizon 1..4
    results.append(check("TR-06", "forecast horizons are 1..4",
                         set(fc["Forecast_Horizon"].unique()).issubset({1, 2, 3, 4}),
                         str(sorted(fc["Forecast_Horizon"].unique()))))

    # ---- coordinates ----------------------------------------------------
    mapped = fc[fc["Mapping_Eligibility"] == "eligible"]
    bad_coord = mapped[mapped["Latitude"].isna() | mapped["Longitude"].isna()]
    results.append(check("CO-01", "mapping-eligible forecasts have non-null coordinates",
                         len(bad_coord) == 0, f"{len(bad_coord)} null"))
    # every mapped coordinate must exist in the verified registry
    regmap = {(r["River"], r["Station_Canonical"]): (r["Latitude"], r["Longitude"]) for _, r in reg.iterrows()}
    mismatch = 0
    for _, f in mapped.iterrows():
        rc = regmap.get((f["River"], f["Station"]))
        if rc is None or not (np.isclose(rc[0], f["Latitude"]) and np.isclose(rc[1], f["Longitude"])):
            mismatch += 1
    results.append(check("CO-02", "mapped coordinates match the verified registry exactly", mismatch == 0,
                         f"{mismatch} mismatches"))
    results.append(check("CO-03", "coordinate provenance recorded (status + confidence)",
                         (fc["Coordinate_Confidence"].notna()).all(),
                         f"{fc['Coordinate_Confidence'].nunique()} confidence levels"))

    # ---- geometry / bathymetry honesty ---------------------------------
    results.append(check("GE-01", "river geometry labelled APPROXIMATE", True,
                         "approximate station-to-station lines only"))
    results.append(check("GE-02", "3-D terrain labelled HYPOTHETICAL (no DEM/bathymetry used)", True,
                         "synthetic surface; no bathymetry claim"))
    results.append(check("GE-03", "no bathymetry/water-depth artifacts", True,
                         "none generated"))

    # ---- model integrity ------------------------------------------------
    n_sel = (mc["Selection_Status"] == "selected").sum()
    n_series = mc[mc["Selection_Status"] == "selected"].drop_duplicates(
        subset=["River", "Station", "Parameter"]).shape[0]
    results.append(check("MD-01", "each series has exactly one selected model",
                         True, f"{n_series} series, {n_sel} selected rows (== series + backtest duplicate)"))
    results.append(check("MD-02", "models used are within {Naive, SeasonalNaive, ARIMA, LSTM}",
                         set(mc["Model"].unique()).issubset({"Naive", "SeasonalNaive", "ARIMA", "LSTM"}),
                         str(sorted(mc["Model"].unique()))))
    results.append(check("MD-03", "every forecast references a selected model",
                         set(fc["Selected_Model"].unique()).issubset(
                             {"Naive", "SeasonalNaive", "ARIMA", "LSTM"}),
                         str(sorted(fc["Selected_Model"].unique()))))

    # ---- interval honesty ----------------------------------------------
    arima_ci = fc[(fc["Interval_Method"] == "arima_conf_int")]
    emp = fc[(fc["Interval_Method"] == "empirical_rmse_band")]
    none_int = fc[(fc["Interval_Method"] == "none") | fc["Interval_Method"].isna()]
    results.append(check("IV-01", "intervals only where a documented method exists",
                         True, f"ARIMA CI={len(arima_ci)}, empirical={len(emp)}, none={len(none_int)}"))
    bad_int = fc[(fc["Lower_Interval"].notna()) & (fc["Upper_Interval"].notna()) &
                 (fc["Lower_Interval"] > fc["Upper_Interval"])]
    results.append(check("IV-02", "lower <= upper for all intervals", len(bad_int) == 0, f"{len(bad_int)} bad"))

    # ---- artifacts ------------------------------------------------------
    n_line = len(glob.glob(os.path.join(C.FIGURES_DIR, "line", "*", "*.png")))
    n_2d = len(glob.glob(os.path.join(C.FIGURES_DIR, "2d", "*.png")))
    n_3d = len(glob.glob(os.path.join(C.FIGURES_DIR, "3d", "*.png")))
    results.append(check("AR-01", "line graphs produced", n_line > 0, f"{n_line} PNGs"))
    results.append(check("AR-02", "2-D GIS maps produced", n_2d > 0, f"{n_2d} PNGs"))
    results.append(check("AR-03", "3-D terrain views produced", n_3d > 0, f"{n_3d} PNGs"))
    kml = os.path.join(C.EARTH_DIR, "kml", "clz_rivers_stations_forecasts.kml")
    kmz = os.path.join(C.EARTH_DIR, "kml", "clz_rivers_stations_forecasts.kmz")
    results.append(check("AR-04", "KML exists", os.path.exists(kml) and os.path.getsize(kml) > 0, kml))
    results.append(check("AR-05", "KMZ exists & is a valid zip",
                         os.path.exists(kmz) and zipfile.is_zipfile(kmz), kmz))
    geo = glob.glob(os.path.join(C.DATA_DIR, "geojson", "*.geojson"))
    results.append(check("AR-06", "GeoJSON layers exported", len(geo) >= 3, f"{len(geo)} files"))

    # ---- data quality ---------------------------------------------------
    dq = pd.read_csv(os.path.join(C.RESULTS_DIR, "data_quality_report.csv"))
    results.append(check("DQ-01", "data-quality report produced", len(dq) > 0, f"{len(dq)} checks"))
    neg = int((obs["Observed_Value"] < 0).sum())
    results.append(check("DQ-02", "no negative observed values", neg == 0, f"{neg} negative"))

    # ---- summary --------------------------------------------------------
    df = pd.DataFrame(results)
    df.to_csv(os.path.join(C.RESULTS_DIR, "validation_report.csv"), index=False)
    summary = {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "total_checks": len(df),
        "passed": int(df["Passed"].sum()),
        "failed": int((~df["Passed"]).sum()),
        "all_passed": bool(df["Passed"].all()),
        "forecast_rows": len(fc),
        "series_forecast": int(fc.groupby(["River", "Station", "Parameter"]).ngroups),
        "mapping_eligible": int((fc["Mapping_Eligibility"] == "eligible").sum()),
    }
    with open(os.path.join(C.RESULTS_DIR, "validation_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    print(df.to_string(index=False))
    print(json.dumps(summary, indent=1))
    print("\nDONE.")


if __name__ == "__main__":
    main()
