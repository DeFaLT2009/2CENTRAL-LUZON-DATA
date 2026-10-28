"""
data_preparation.py
===================
Stage 4 of the pipeline.

Takes the raw standardised long table (``observations_long.csv``) and the
station registry, then builds the analysis-ready datasets:

* ``data/processed/observations_monthly.csv``   - monthly observations
* ``data/processed/observations_quarterly.csv`` - quarterly aggregates
* ``data/processed/series_inventory.csv``        - one row per river/station/parameter
* ``results/data_quality_report.csv``            - validation / QC findings

Rules (all documented, no future information used):

* Only ``river``-type waterbodies that appear in the registry AND have at
  least one resolved coordinate are used for the *spatial* analysis.  All
  waterbodies remain in the inventory for audit.
* Only parameters with defined metadata are kept as modelling targets.
* Asterisks / dashes / unparseable cells were already marked ``missing`` /
  ``invalid`` at extraction time and are excluded from values, but their
  count is reported.
* Monthly records are aggregated to quarters by the mean of available months;
  the number of contributing months is retained (``N_Months``).
* Direct quarterly records (from the quarterly worksheet variant) are kept as
  ``Data_Granularity = 'quarterly_report'``.

Usage
-----
    python code/data_preparation.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402
from discover_and_verify_stations import core_station  # noqa: E402

C.ensure_dirs()

VALID_STATUS = {"ok", "detection_limit"}
MODEL_PARAM_WHITELIST = set(C.PARAM_META.keys())


def load_inputs():
    obs = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_long.csv"))
    inv = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    coords = pd.read_csv(os.path.join(C.REGISTRY_DIR, "verified_coordinates.csv"))
    return obs, inv, coords


def build_series_inventory(obs_valid, inv):
    """One row per (river, station, parameter) with completeness stats."""
    ov = obs_valid.copy()
    ov["Qkey"] = ov["Year"].astype(int) * 10 + ov["Quarter"].astype(int)
    g = (ov.groupby(["River", "Station", "Parameter"])
         .agg(N_Observations=("Observed_Value", "size"),
              N_Quarters=("Qkey", "nunique"),
              First_Date=("Date", "min"),
              Last_Date=("Date", "max"))
         .reset_index())
    g["Series_ID"] = (g["River"] + "|" + g["Station"] + "|" + g["Parameter"])
    return g


def main():
    print("=" * 80)
    print("STAGE 4  -  DATA VALIDATION & QUARTERLY PREPARATION")
    print("=" * 80)
    obs, inv, coords = load_inputs()

    # ---- 1. attach verified coordinates -----------------------------------
    # Use the deduplicated coordinate layer (one row per River + canonical
    # station) so the merge cannot duplicate observations.  Workbook station
    # labels are reduced with the same core_station() normaliser the registry
    # used, so e.g. "Deca Homes" and "Marilao Caloocan Bridge" align.
    coords = coords.copy()
    coords["_key"] = (coords["River"].astype(str).str.strip().str.upper() + "|"
                      + coords["Station_Canonical"].astype(str).str.strip().str.upper())
    coords = coords.drop_duplicates("_key", keep="first")
    obs["_key"] = (obs["River"].astype(str).str.strip().str.upper() + "|"
                   + obs["Station_Name"].map(core_station).astype(str).str.strip().str.upper())
    obs = obs.merge(
        coords[["_key", "Station_Canonical", "Latitude", "Longitude",
               "Coordinate_Confidence", "Coordinate_Status"]],
        on="_key", how="left",
    )
    obs["Station_Canonical"] = obs["Station_Canonical"].fillna(obs["Station_Name"])
    obs = obs.drop(columns=["_key"])

    # ---- 2. parameter whitelist & value filtering -----------------------
    obs["Param_Whitelisted"] = obs["Parameter_Canonical"].isin(MODEL_PARAM_WHITELIST)
    obs_valid = obs[obs["Value_Status"].isin(VALID_STATUS) & obs["Param_Whitelisted"]].copy()
    obs_valid = obs_valid.dropna(subset=["Value"])
    obs_valid["Value"] = obs_valid["Value"].astype(float)

    print(f"raw rows                : {len(obs)}")
    print(f"rows with usable values : {len(obs_valid)}")
    print(f"distinct parameters     : {obs_valid['Parameter_Canonical'].nunique()}")

    # ---- 3. monthly table ------------------------------------------------
    monthly = obs_valid[obs_valid["Period_Type"] == "month"].copy()
    monthly["Date"] = pd.to_datetime(dict(year=monthly["Year"].astype(int),
                                          month=monthly["Month"].astype(int),
                                          day=1))
    monthly = monthly.sort_values(["River", "Station_Canonical", "Parameter_Canonical", "Date"])
    monthly.to_csv(os.path.join(C.PROCESSED_DIR, "observations_monthly.csv"), index=False)

    # ---- 4. quarterly aggregation ---------------------------------------
    recs = []
    for (river, stn, param), grp in obs_valid.groupby(["River", "Station_Canonical", "Parameter_Canonical"]):
        for (yr, q), qg in grp.groupby(["Year", "Quarter"]):
            if q is None or pd.isna(q):
                continue
            qmonths = qg[qg["Period_Type"] == "month"]
            if len(qmonths):
                vals = qmonths["Value"].astype(float)
                val = float(vals.mean())
                n_months = int(vals.count())
                gran = "monthly_aggregated"
            else:
                qd = qg[qg["Period_Type"] == "quarter"]
                if not len(qd):
                    continue
                val = float(qd["Value"].astype(float).mean())
                n_months = 3
                gran = "quarterly_report"
            dt = pd.Timestamp(int(yr), 3 * int(q) - 1, 15)
            recs.append({
                "River": river,
                "Station": stn,
                "Station_ID": f"{river}|{stn}",
                "Parameter": param,
                "Unit": C.param_unit(param),
                "Parameter_Kind": C.param_kind(param),
                "Year": int(yr),
                "Quarter": int(q),
                "Date": dt,
                "Observed_Value": val,
                "N_Months": n_months,
                "Data_Granularity": gran,
                "Latitude": float(grp["Latitude"].iloc[0]) if pd.notna(grp["Latitude"].iloc[0]) else np.nan,
                "Longitude": float(grp["Longitude"].iloc[0]) if pd.notna(grp["Longitude"].iloc[0]) else np.nan,
                "Coordinate_Confidence": grp["Coordinate_Confidence"].iloc[0],
                "Source_Files": "; ".join(sorted(set(grp["Source_File"]))),
            })
    q = pd.DataFrame(recs).sort_values(["River", "Station", "Parameter", "Date"]).reset_index(drop=True)
    q.to_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"), index=False)

    print(f"quarterly rows          : {len(q)}  "
          f"(series: {q.groupby(['River','Station','Parameter']).ngroups})")

    # ---- 5. series inventory --------------------------------------------
    inv_series = build_series_inventory(q, inv)
    inv_series.to_csv(os.path.join(C.PROCESSED_DIR, "series_inventory.csv"), index=False)

    # ---- 6. data-quality report -----------------------------------------
    dq = []
    def add(check, value, note):
        dq.append({"Check": check, "Value": value, "Note": note})

    add("source_workbooks", len(C.EXCEL_FILES), "; ".join(C.EXCEL_FILES))
    add("raw_observation_rows", len(obs), "all cells parsed from workbooks")
    add("usable_value_rows", len(obs_valid), "ok/detection_limit + whitelisted parameter")
    add("missing_value_rows", int((obs["Value_Status"] == "missing").sum()), "asterisks/dashes/blank")
    add("invalid_value_rows", int((obs["Value_Status"] == "invalid").sum()), "unparseable text")
    add("detection_limit_rows", int((obs["Value_Status"] == "detection_limit").sum()), "values below reporting limit")
    add("non_parameter_rows", int((~obs["Param_Whitelisted"]).sum()), "labels that are not water-quality parameters")
    add("distinct_rivers_all", obs["River"].nunique(), "including coastal/marine waterbodies")
    add("distinct_rivers_river_type", int((obs["Waterbody_Type"] == "river").sum()), "rows flagged river-type")
    add("distinct_stations", obs["Station_Canonical"].nunique(), "normalised station identities")
    add("distinct_parameters", obs_valid["Parameter_Canonical"].nunique(), "; ".join(sorted(obs_valid['Parameter_Canonical'].unique())))
    add("quarterly_series_total", int(inv_series.shape[0]), "river/station/parameter series")
    add("quarterly_series_ge12", int((inv_series["N_Observations"] >= 12).sum()), "series with >=12 quarterly observations")
    add("coordinate_unresolved_rows", int((obs["Coordinate_Status"] == "unresolved").sum()), "no coordinate source matched")
    add("coordinate_duplicate_clusters", int(pd.read_csv(os.path.join(C.REGISTRY_DIR, "duplicate_coordinates.csv")).shape[0]),
        "same lat/lon shared by multiple stations")

    # duplicate measurements check
    dupmask = obs_valid.duplicated(subset=["River", "Station_Canonical", "Parameter_Canonical", "Date"], keep=False)
    add("duplicate_measurement_rows", int(dupmask.sum()), "same station/param/date appearing more than once")

    # unit consistency
    u = obs_valid.groupby("Parameter_Canonical")["Unit"].nunique()
    add("parameters_with_multiple_units", int((u > 1).sum()), "unit inconsistency count")

    # suspicious values
    add("negative_value_rows", int((obs_valid["Value"] < 0).sum()), "negative measurements (should be none)")

    dqdf = pd.DataFrame(dq)
    dqdf.to_csv(os.path.join(C.RESULTS_DIR, "data_quality_report.csv"), index=False)
    print("\nData-quality report:")
    print(dqdf.to_string(index=False))

    # ---- 7. eligible series summary ------------------------------------
    elig = inv_series[inv_series["N_Observations"] >= 8].copy()
    print(f"\nSeries with >=8 quarterly observations: {len(elig)}")
    print(elig.groupby("River").size().sort_values(ascending=False).head(25).to_string())
    print("\nDONE.")


if __name__ == "__main__":
    main()
