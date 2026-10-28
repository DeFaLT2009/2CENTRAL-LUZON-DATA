"""
discover_and_verify_stations.py
================================
Stage 3 of the pipeline.

Builds the auditable station-coordinate registry for Central Luzon (Region III)
by combining **three** independent sources that actually exist in the repository:

1. ``sampling station coords.xlsx - merged.csv``  (shapefile attribute export,
   the repository's primary station-coordinate table).
2. ``Future-predictor8.py``  (``STATION_COORDS`` dictionary - supplies
   coordinates that the merged CSV leaves as ``0,0`` placeholders).
3. The station names that actually appear in the water-quality workbooks
   (``observations_long.csv``).

Outputs
-------
    data/station_registry/station_inventory.csv
    data/station_registry/verified_coordinates.csv
    data/station_registry/coordinate_sources.csv
    data/station_registry/coordinate_conflicts.csv

Every coordinate keeps its provenance (source file, source path, record id) and
a confidence / status assessment.  Conflicting values are preserved, never
silently overwritten.

Usage
-----
    python code/discover_and_verify_stations.py
"""

from __future__ import annotations

import os
import re
import ast
import sys
import json
import datetime as _dt

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

# ----------------------------------------------------------------------------
# Station-name normalisation
# ----------------------------------------------------------------------------
JUNK_STATION_TOKENS = {
    "AVERAGE", "MAXIMUM", "MINIMUM", "DATE", "DATE OF SAMPLING",
    "BALANGA BATAAN", "PAMPANGA", "MARILAO BULACAN", "MEYCAUAYAN BULACAN",
    "CALUMPIT PAMPANGA", "TALISAY RIVER", "OBANDO BULACAN",
}

# Curated, documented identity resolutions.  Each entry records *why* two
# worksheet spellings refer to the same physical sampling station.
STATION_ALIASES = {
    # spelling / abbreviation variants
    "MC ARTHUR BRIDGE": "MCARTHUR BRIDGE",
    "MCARTHUR HIGHWAY": "MCARTHUR BRIDGE",          # Meycauayan McArthur Bridge
    "NEAR BANSON RESIDENCE": "NEAR BANZON RESIDENCE",
    "UP STREAM": "UPSTREAM",
    "DOWN STREAM": "DOWNSTREAM",
    "MID STREAM": "MIDSTREAM",
    "MID STREAM": "MIDSTREAM",
    "CUT CUT BRIDGE": "CUTCUT BRIDGE",
    "CUTCUT BRIDGE": "CUTCUT CAPAS BRIDGE",  # Cut-Cut Bridge (workbook) = Cutcut Capas Bridge (coord CSV)
    "BRIDGE NEARVILLA": "BRIDGE NEAR VILLA SANTIAGO COMPOUND",
    "SAN VICENTE BRIDGE 3": "SAN VICENTE BRIDGE",
    "BALIUAG BUSTOS BRIDGE": "BALIWAG BUSTOS BRIDGE",
    "PULILAN PLARIDEL BRIDGE": "PLARIDEL PULILAN BRIDGE",
    "PLAZA BURGOS": "PLAZA BURGOS BRIDGE",
    "FISHPORT NEAR PUBLIC MARKET": "FISHPORT PUBLIC MARKET",
    "NEAR MUNICIPAL FISHPORT P M": "FISHPORT PUBLIC MARKET",
    "MUNICIPAL FISHPORT NEAR PUBLIC MARKET": "FISHPORT PUBLIC MARKET",
    "OBANDO RIVER MOUTH OF OBANDO RIVER": "OBANDO RIVER",
    "NEAR VILLA LOURDES RESORT": "VILLA LOURDES RESORT",
    "VILLA LOURDES": "VILLA LOURDES RESORT",
    "TALISAY RIVER": "TALISAY RIVER",
    # documented station renames / identity resolutions
    "DECA HOMES": "MARILAO CALOOCAN BRIDGE",   # Deca Homes subdivision sits at the
                                               # Marilao-Caloocan boundary bridge
    "BALIWAG": "BALIWAG BUSTOS BRIDGE",
    "PULILAN": "PLARIDEL PULILAN BRIDGE",
    "TALISAY RIVER UPSTREAM 1": "TALISAY RIVER UPSTREAM 1",
}

# Mouth-of-river monitoring sections belong to the parent river system.
RIVER_PARENT = {
    "MOUTH OF PAMPANGA": "Pampanga River",
    "MOUTH OF OBANDO": "Obando River",
    "MOUTH OF TALISAY": "Talisay River",
    "TALISAY RIVER UPSTREAM": "Talisay River",
}


def core_station(s: str) -> str:
    """Reduce a messy worksheet station label to a comparable core name."""
    s = str(s)
    s = re.split(r"\s{2,}|\n", s)[0]                 # drop address block
    s = re.split(r"\b(?:brgy|barangay|sitio|blg|poblacion|pueblo)\b", s, flags=re.I)[0]
    s = s.split("(")[0]                              # drop parenthetical
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    m = re.match(r"^300\s*(?:M|METERS|MTRS)?\s*AWAY\s+FROM\s+ST(?:A|ATION)?\.?\s*(\d+)", s)
    if m:
        return f"MOUTH STATION {m.group(1)}"
    s = re.sub(r"^STATION\s+\d+\s*", "", s)          # "Station 3 Expressway Bridge"
    if s in JUNK_STATION_TOKENS:
        return ""
    # apply aliases transitively so chains ("CUT CUT BRIDGE" -> "CUTCUT BRIDGE"
    # -> "CUTCUT CAPAS BRIDGE") resolve to the final canonical name
    seen = set()
    while s in STATION_ALIASES and s not in seen:
        seen.add(s)
        s = STATION_ALIASES[s]
    return s


def river_canonical(river: str) -> str:
    r = C.normalize_river_name(river)
    up = r.upper()
    for k, v in RIVER_PARENT.items():
        if k in up:
            return v
    return r


# ----------------------------------------------------------------------------
# Source loaders
# ----------------------------------------------------------------------------
def load_coord_csv() -> list[dict]:
    path = os.path.join(C.REPO_ROOT, C.COORD_CSV)
    df = pd.read_csv(path)
    recs = []
    for idx, r in df.iterrows():
        river_raw = r["layer"]
        if not pd.notna(river_raw) or str(river_raw).strip().lower() in {"", "nan", "additional monitored rivers"}:
            river_raw = r["Waterbody_"] if pd.notna(r["Waterbody_"]) else r["WB_Name"]
        station = None
        for col in ("STN_ID", "Station_ID", "NAME"):
            v = r[col]
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() not in {"nan"}:
                station = str(v).strip()
                break
        lat = r["LAT"] if pd.notna(r["LAT"]) else np.nan
        lon = r["LONG"] if pd.notna(r["LONG"]) else np.nan
        if station is None:
            continue
        river_canon = C.river_from_station(station, river_canonical(str(river_raw)))
        if not core_station(station):
            continue
        recs.append({
            "River_Raw": str(river_raw),
            "River": river_canon,
            "Station": station,
            "Station_Core": core_station(station),
            "Latitude": lat,
            "Longitude": lon,
            "Source_File": C.COORD_CSV,
            "Source_Path": str(r.get("path", "")),
            "Source_Record_ID": f"CSV:{idx}",
            "Source_Type": "merged_shapefile_attributes",
        })
    return recs


def load_script_coords() -> list[dict]:
    path = os.path.join(C.REPO_ROOT, C.ORIGINAL_SCRIPT)
    txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    m = re.search(r"STATION_COORDS\s*=\s*(\{.*?\n\})", txt, re.S)
    if not m:
        return []
    coords = ast.literal_eval(m.group(1))
    river_map = {
        "RIO CHICO BRIDGE": "Rio Chico River",
        "SAN VICENTE BRIDGE": "Rio Chico River",
        "PASANG INCHIC BRIDGE": "Rio Chico River",
        "CUTCUT CAPAS BRIDGE": "Lucong River",
        "SANTIAGO BRIDGE": "Lucong River",
        "NEAR GREEN VILLAGE": "Lucong River",
    }
    recs = []
    for k, v in coords.items():
        recs.append({
            "River_Raw": river_map.get(k, k),
            "River": river_map.get(k, river_canonical(k)),
            "Station": k,
            "Station_Core": core_station(k),
            "Latitude": float(v["Latitude"]),
            "Longitude": float(v["Longitude"]),
            "Source_File": C.ORIGINAL_SCRIPT,
            "Source_Path": f"GitHub:{C.ORIGINAL_SCRIPT}",
            "Source_Record_ID": f"SCRIPT:{k}",
            "Source_Type": "python_station_coords_dict",
        })
    return recs


def load_workbook_stations() -> pd.DataFrame:
    obs_path = os.path.join(C.PROCESSED_DIR, "observations_long.csv")
    if not os.path.exists(obs_path):
        raise SystemExit("observations_long.csv not found - run inspect_excel_workbooks.py first")
    obs = pd.read_csv(obs_path)
    obs = obs[obs["Value_Status"].isin(["ok", "detection_limit"])]
    wb = (obs.groupby(["River", "Station_Name"])
          .agg(Obs_Count=("Value", "size"),
               Param_Count=("Parameter_Canonical", "nunique"),
               First_Year=("Year", "min"),
               Last_Year=("Year", "max"))
          .reset_index())
    wb["Station_Core"] = wb["Station_Name"].apply(core_station)
    wb["River_Canonical"] = wb["River"].apply(river_canonical)
    return wb


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    print("=" * 80)
    print("STAGE 3  -  STATION & COORDINATE REGISTRY DISCOVERY")
    print("=" * 80)

    coord_recs = load_coord_csv()
    script_recs = load_script_coords()
    wb = load_workbook_stations()

    # --- build coordinate lookup keyed by (river, station_core) -------------
    coords = pd.DataFrame(coord_recs + script_recs)
    coords["River"] = coords["River"].apply(river_canonical)
    coords["Station_Core"] = coords["Station_Core"].apply(lambda s: s or "")

    def valid(row):
        return C.coords_in_philippines(row["Latitude"], row["Longitude"])

    coords["coords_ok"] = coords.apply(valid, axis=1)

    # resolve 0/0 placeholders and lat/lon swaps
    def resolve(row):
        lat, lon = row["Latitude"], row["Longitude"]
        note = []
        if pd.isna(lat) or pd.isna(lon):
            return lat, lon, "missing", note
        if lat == 0 and lon == 0:
            return lat, lon, "placeholder_zero", note
        # swap detection
        if not (-90 <= lat <= 90) and -180 <= lon <= 180:
            lat, lon = lon, lat
            note.append("lat/lon swapped to place point in Philippines")
        if not C.coords_in_philippines(lat, lon):
            note.append("outside Philippines bounds")
        return lat, lon, ("ok" if not note else "suspect"), note

    resolved = coords.apply(resolve, axis=1, result_type="expand")
    coords["Latitude_R"] = resolved[0]
    coords["Longitude_R"] = resolved[1]
    coords["Coord_Flag"] = resolved[2]
    coords["Coord_Note"] = resolved[3].apply(lambda x: "; ".join(x) if isinstance(x, list) else str(x))

    # --- aggregate coordinate sources per (river, station_core) -------------
    key_cols = ["River", "Station_Core"]
    def agg(grp):
        sources = sorted(set(grp["Source_File"]))
        paths = sorted(set(grp["Source_Path"]))
        recs = sorted(set(grp["Source_Record_ID"]))
        nz = grp[grp["Coord_Flag"] != "placeholder_zero"]
        if len(nz) == 0 or nz["Latitude_R"].dropna().empty:
            return pd.Series({
                "Latitude": np.nan, "Longitude": np.nan,
                "Source_File": "; ".join(sources),
                "Source_Path": "; ".join(paths),
                "Source_Record_ID": "; ".join(recs),
                "Coordinate_Confidence": "Unverified",
                "Coordinate_Status": "unresolved",
                "Verification_Notes": "no usable coordinate in any source",
                "N_Sources": len(sources),
            })
        lats = sorted(nz["Latitude_R"].dropna().unique().tolist())
        lons = sorted(nz["Longitude_R"].dropna().unique().tolist())
        has_zero = bool((grp["Coord_Flag"] == "placeholder_zero").any())
        lat, lon = float(lats[0]), float(lons[0])
        if len(lats) == 1 and len(lons) == 1:
            conf, status = "High", "verified"
            note = "single consistent coordinate across sources"
            if has_zero:
                status = "corrected_from_placeholder"
                note = ("merged CSV contains a 0,0 placeholder; resolved using "
                        f"{nz['Source_File'].iloc[0]}")
        elif len(lats) == 1:
            conf, status = "High", "verified"
            note = "latitude consistent; longitude varied"
        else:
            conf, status = "Conflict", "conflicting_coordinates"
            note = f"conflicting values {lats}"
        return pd.Series({
            "Latitude": lat, "Longitude": lon,
            "Source_File": "; ".join(sources),
            "Source_Path": "; ".join(paths),
            "Source_Record_ID": "; ".join(recs),
            "Coordinate_Confidence": conf,
            "Coordinate_Status": status,
            "Verification_Notes": note,
            "N_Sources": len(sources),
        })

    reg = coords.groupby(key_cols, dropna=False).apply(agg, include_groups=False).reset_index()
    reg = reg.rename(columns={"Station_Core": "Station_Canonical"})

    # --- merge workbook stations ---------------------------------------------
    wb_keys = wb[["River_Canonical", "Station_Core", "Station_Name", "Obs_Count",
                  "Param_Count", "First_Year", "Last_Year"]].copy()
    wb_keys = wb_keys.rename(columns={"River_Canonical": "River", "Station_Core": "Station_Canonical"})
    inv = wb_keys.merge(reg, on=["River", "Station_Canonical"], how="left")
    inv["Station_ID"] = (inv["River"] + "|" + inv["Station_Canonical"])
    inv["Coordinate_Confidence"] = inv["Coordinate_Confidence"].fillna("Unverified")
    inv["Coordinate_Status"] = inv["Coordinate_Status"].fillna("unresolved")
    inv["Verification_Notes"] = inv["Verification_Notes"].fillna("no coordinate source matched")
    inv["Coordinate_Source_File"] = inv["Source_File"].fillna("none")
    inv["Coordinate_Source_Path"] = inv["Source_Path"].fillna("none")
    inv["Coordinate_Source_Record_ID"] = inv["Source_Record_ID"].fillna("none")
    inv["Original_Station_Name"] = inv["Station_Name"]
    inv["Mapping_Confidence"] = np.where(inv["Station_Canonical"] == "", "Unmapped", "Normalized")

    # reorder columns for the required schema
    inv = inv[[
        "River", "Station_Canonical", "Station_ID", "Original_Station_Name",
        "Latitude", "Longitude", "Coordinate_Source_File", "Coordinate_Source_Path",
        "Coordinate_Source_Record_ID", "Coordinate_Confidence", "Coordinate_Status",
        "Verification_Notes", "N_Sources", "Obs_Count", "Param_Count",
        "First_Year", "Last_Year", "Mapping_Confidence",
    ]].sort_values(["River", "Station_Canonical"]).reset_index(drop=True)

    inv.to_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"), index=False)
    reg.to_csv(os.path.join(C.REGISTRY_DIR, "verified_coordinates.csv"), index=False)

    # coordinate provenance / source table
    src = (coords.groupby("Source_File")
           .agg(Records=("Source_Record_ID", "size"),
                Waterbodies=("River", "nunique"))
           .reset_index())
    src.to_csv(os.path.join(C.REGISTRY_DIR, "coordinate_sources.csv"), index=False)

    # conflicts
    conf = (coords.groupby(["River", "Station_Core"])
            .size().reset_index(name="N_Records"))
    conf = conf[conf["N_Records"] > 1]
    conf.to_csv(os.path.join(C.REGISTRY_DIR, "coordinate_conflicts.csv"), index=False)

    print(f"Coordinate sources: {len(coords)} raw records "
          f"({coords['Source_File'].nunique()} files)")
    print(f"Distinct waterbodies in registry: {reg['River'].nunique()}")
    print(f"Distinct stations in registry: {reg['Station_Canonical'].nunique()}")
    print(f"Workbook stations: {len(wb)}")
    print(f"Station inventory rows: {len(inv)}")
    print("\nCoordinate status:")
    print(inv["Coordinate_Status"].value_counts().to_string())
    print("\nUnresolved (no coordinate) stations:")
    un = inv[inv["Coordinate_Status"] == "unresolved"]
    print(un[["River", "Station_Canonical", "Obs_Count"]].head(40).to_string(index=False))
    print(f"\n... total unresolved: {len(un)}")

    # duplicate-coordinate audit (same lat/lon used by unrelated stations)
    dup = (inv[inv["Latitude"].notna()]
           .groupby(["Latitude", "Longitude"])
           .agg(N=("Station_ID", "size"), Stations=("Station_ID", lambda s: "; ".join(s)))
           .reset_index())
    dup = dup[dup["N"] > 1]
    dup.to_csv(os.path.join(C.REGISTRY_DIR, "duplicate_coordinates.csv"), index=False)
    print(f"\nDuplicate coordinate clusters: {len(dup)}")


if __name__ == "__main__":
    main()
