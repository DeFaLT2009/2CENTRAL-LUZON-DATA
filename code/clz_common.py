"""
clz_common.py
=============
Shared configuration, paths, parameter metadata, river-name normalisation and
low-level parsing helpers for the Central Luzon (Region III) river
forecasting + GIS pipeline.

This module is deliberately dependency-light (pandas / numpy only) so that it
can be imported by every stage script.

The repository root is discovered relative to this file: .../code/clz_common.py
-> repository root is the parent directory of ``code``.
"""

from __future__ import annotations

import os
import re
import json
import datetime as _dt
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------
# Repository / project layout
# ----------------------------------------------------------------------------
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CODE_DIR)

DATA_DIR = os.path.join(REPO_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw", "Excel")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
FORECAST_DIR = os.path.join(DATA_DIR, "forecasts")
REGISTRY_DIR = os.path.join(DATA_DIR, "station_registry")
GEO_DIR = os.path.join(DATA_DIR, "geographic")

MODELS_DIR = os.path.join(REPO_ROOT, "models")
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIGURES_DIR = os.path.join(REPO_ROOT, "figures")
GIS_DIR = os.path.join(REPO_ROOT, "GIS")
EARTH_DIR = os.path.join(REPO_ROOT, "Google_Earth_Pro")
DOC_DIR = os.path.join(REPO_ROOT, "documentation")

ALL_DIRS = [
    DATA_DIR, RAW_DIR, PROCESSED_DIR, FORECAST_DIR, REGISTRY_DIR, GEO_DIR,
    MODELS_DIR, RESULTS_DIR, FIGURES_DIR, GIS_DIR, EARTH_DIR, DOC_DIR,
    os.path.join(MODELS_DIR, "model_configurations"),
    os.path.join(MODELS_DIR, "checkpoints"),
    os.path.join(FIGURES_DIR, "line"),
    os.path.join(FIGURES_DIR, "2d"),
    os.path.join(FIGURES_DIR, "3d"),
]

for _d in ALL_DIRS:
    os.makedirs(_d, exist_ok=True)

# Canonical source workbooks (these are the actual repository files).
EXCEL_FILES = [
    "2017.xlsx", "2018.xlsx", "2019.xlsx", "2020.xlsx", "2021.xlsx",
    "2022.xlsx", "2023.xlsx", "2024.xlsx", "2025.xlsx",
    "January to June 2026.xlsx",
]
COORD_CSV = "sampling station coords.xlsx - merged.csv"
ORIGINAL_SCRIPT = "Future-predictor8.py"


def ensure_dirs() -> None:
    for _d in ALL_DIRS:
        os.makedirs(_d, exist_ok=True)


# ----------------------------------------------------------------------------
# Run metadata
# ----------------------------------------------------------------------------
RUN_STAMP = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, _dt.datetime, _dt.date)):
        return str(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    raise TypeError(f"Object of type {type(o)} is not JSON serialisable")


# ----------------------------------------------------------------------------
# Water-quality parameter metadata
# ----------------------------------------------------------------------------
# Canonical parameter name -> (display name, unit, kind, orientation)
#   kind: 'microbial' | 'chemical' | 'physical' | 'other'
#   orientation: 'high_bad' (higher = worse) | 'low_bad' (lower = worse, e.g. DO)
#                | 'range' (must fall inside a band, e.g. pH, temperature)
PARAM_META = {
    "DO":        {"display": "Dissolved Oxygen",      "unit": "mg/L",      "kind": "chemical", "orientation": "low_bad"},
    "BOD":       {"display": "Biochemical Oxygen Demand", "unit": "mg/L",  "kind": "chemical", "orientation": "high_bad"},
    "TSS":       {"display": "Total Suspended Solids", "unit": "mg/L",      "kind": "physical", "orientation": "high_bad"},
    "pH":        {"display": "pH",                     "unit": "-",         "kind": "chemical", "orientation": "range"},
    "Temp":      {"display": "Temperature",           "unit": "deg C",     "kind": "physical", "orientation": "range"},
    "Color":     {
        "display": "Color", "unit": "TCU", "kind": "physical", "orientation": "high_bad"},
    "Fecal Coliform": {"display": "Fecal Coliform", "unit": "MPN/100mL", "kind": "microbial", "orientation": "high_bad"},
    "NO3-N":     {"display": "Nitrates (NO3-N)",      "unit": "mg/L",      "kind": "chemical", "orientation": "high_bad"},
    "PO4-P":     {"display": "Phosphates (PO4-P)",    "unit": "mg/L",      "kind": "chemical", "orientation": "high_bad"},
    "Cl":        {"display": "Chloride (Cl-)",        "unit": "mg/L",      "kind": "chemical", "orientation": "high_bad"},
    "NH3":       {"display": "Ammonia (NH3-N)",       "unit": "mg/L",      "kind": "chemical", "orientation": "high_bad"},
    "Metals":    {"display": "Metals",                "unit": "mg/L",      "kind": "other",    "orientation": "high_bad"},
}

# Parameter display-name fragments -> canonical key (order matters: first match wins)
PARAM_PATTERNS = [
    (r"fecal\s*coliform", "Fecal Coliform"),
    (r"\bE\.?\s*coli\b", "E. coli"),
    (r"total\s*coliform", "Total Coliform"),
    (r"\bDO\b|dissolved\s*oxygen", "DO"),
    (r"\bBOD\b|biochemical\s*oxygen", "BOD"),
    (r"\bTSS\b|total\s*suspended\s*solids", "TSS"),
    (r"\bpH\b", "pH"),
    (r"temp", "Temp"),
    (r"color|colour", "Color"),
    (r"nitrate|\bno3", "NO3-N"),
    (r"phosphate|\bpo4", "PO4-P"),
    (r"chloride|\bcl-\b|\bcl\b", "Cl"),
    (r"ammonia|\bnh3", "NH3"),
    (r"conductivity", "Conductivity"),
    (r"salinity", "Salinity"),
    (r"\bTDS\b|total\s*dissolved\s*solids", "TDS"),
    (r"oxidation|reduction|\bORP\b", "ORP"),
]

# extra metadata for parameters discovered in the workbooks
PARAM_META.update({
    "Total Coliform": {"display": "Total Coliform", "unit": "MPN/100mL", "kind": "microbial", "orientation": "high_bad"},
    "Conductivity":   {"display": "Conductivity", "unit": "mS/cm", "kind": "physical", "orientation": "high_bad"},
    "Salinity":       {"display": "Salinity", "unit": "psu", "kind": "physical", "orientation": "high_bad"},
    "TDS":            {"display": "Total Dissolved Solids", "unit": "mg/L", "kind": "physical", "orientation": "high_bad"},
    "ORP":            {"display": "Oxidation-Reduction Potential", "unit": "mV", "kind": "chemical", "orientation": "high_bad"},
    "E. coli":        {"display": "Escherichia coli", "unit": "MPN/100mL", "kind": "microbial", "orientation": "high_bad"},
})

# ----------------------------------------------------------------------------
# DENR Water Quality Guidelines (Class C) used by the source workbooks.
# Values are taken verbatim from the repository workbook sheets
# 'WQG FOR CLASS C' (2023.xlsx) and the 'WQG' column of the 2025/2026 sheets.
# ----------------------------------------------------------------------------
WQG_CLASS_C = {
    "DO":        {"value": 5.0,  "rule": "min",  "note": "DO >= 5.0 mg/L"},
    "BOD":       {"value": 7.0,  "rule": "max",  "note": "BOD <= 7.0 mg/L"},
    "TSS":       {"value": 80.0, "rule": "max",  "note": "TSS <= 80 mg/L"},
    "pH":        {"value": (6.5, 9.0), "rule": "range", "note": "pH 6.5-9.0"},
    "Temp":      {"value": (25.0, 31.0), "rule": "range", "note": "Temp 25-31 deg C"},
    "Color":     {"value": 75.0, "rule": "max",  "note": "Color <= 75 TCU"},
    "Fecal Coliform": {"value": 200.0, "rule": "max", "note": "FC <= 200 MPN/100mL"},
    "NO3-N":     {"value": 10.0, "rule": "max",  "note": "NO3-N <= 10 mg/L (DENR general)"},
    "PO4-P":     {"value": 0.2,  "rule": "max",  "note": "PO4-P <= 0.2 mg/L (DENR general)"},
    "Cl":        {"value": 250.0, "rule": "max", "note": "Cl- <= 250 mg/L (DENR general)"},
}

# ----------------------------------------------------------------------------
# River-name normalisation
# ----------------------------------------------------------------------------
# Maps the (messy) worksheet names to a canonical river / waterbody key and
# classifies each as a river or a non-river (coastal / marine / bathing) body.
RIVER_ALIASES = {
    "marilao": "Marilao River",
    "meycauayan": "Meycauayan River",
    "obando": "Obando River",
    "bocaue": "Bocaue River",
    "sta. maria": "Santa Maria River",
    "sta maria": "Santa Maria River",
    "santa maria": "Santa Maria River",
    "pampanga": "Pampanga River",
    "angat": "Angat River",
    "r4l": "Angat River",
    "guagua": "Guagua River",
    "talisay": "Talisay River",
    "atlag": "Atlag River",
    "labangan": "Labangan River",
    "hagonoy": "Hagonoy River",
    "san miguel": "San Miguel River",
    "balaong": "Balaong River",
    "madlum": "Madlum River",
    "lucong": "Lucong River",
    "rio chico": "Rio Chico River",
    "rio chico (tarlac)": "Rio Chico River",
    "rio chico tarlac": "Rio Chico River",
    "rio chico nueva ecija": "Rio Chico River",
    "quitangil": "Quitangil River",
    "malimba": "Malimba River",
    "dibalo": "Dibalo River",
    "pudoc": "Pudoc River",
    "nambaralan": "Nambalan River",
    "pasig poterero": "PASIG Potrero River",
    "sacobia": "Sacobia River",
    "morong": "Morong River",
    "almacen": "Almacen River",
    "labong": "Labong River",
    "batang": "Bataan River",
    "bagsit": "Bagsit River",
    "talavera": "Talavera River",
    "palakol": "Palakol River",
    "dicaloyungan": "Dicaloyungan River",
    "subic": "Subic River",
    "zambales bay": "Zambales Bay",
    "baler bay": "Baler Bay",
    "bataan": "Bataan River",
    "batang": "Bataan River",
    "asfmsrs": "ASFMSRS WQMA",
    "a-sf-m-s": "ASFMSRS WQMA",
    "asfmsrs wqma": "ASFMSRS WQMA",
    "mouth of pampanga": "Pampanga River",
    "mouth of obando": "Obando River",
    "mouth of talisay": "Talisay River",
    "pampanga upstream": "Pampanga River Upstream",
    "pampanga up stream": "Pampanga River Upstream",
    "pampanga up-stream": "Pampanga River Upstream",
    "rio chico tarlac": "Rio Chico River",
    "rio chico de tarlac": "Rio Chico River",
    "tarlac rio chico": "Rio Chico River",
    "pampanga river nueva ecija": "Pampanga River Nueva Ecija",
}

# Sheet-name fragments that indicate coastal / marine / bathing / offshore
# sampling (excluded from *river* forecasting, kept for the data inventory).
NON_RIVER_PATTERNS = [
    "coast", "beach", "bay", "offshore", "bather", "bathing", "mariveles",
    "limay", "montemar", "juness", "mouth of", "subic", "zambales bay",
    "baler bay", "near river", "swimmable",
]

MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _clean_name(name: str) -> str:
    key = re.sub(r"[\(\)\[\]/,_]", " ", str(name).strip().upper())
    return re.sub(r"\s+", " ", key).strip()


def normalize_river_name(sheet_name: str) -> str:
    """Return a canonical river key for a worksheet name (best effort)."""
    key = _clean_name(sheet_name)
    low = key.lower()
    if low in RIVER_ALIASES:
        return RIVER_ALIASES[low]
    for frag, canon in RIVER_ALIASES.items():
        if frag in low:
            return canon
    return key if key else "UNKNOWN"


def normalize_waterbody(name: str) -> str:
    """Canonical waterbody key for a free-text waterbody/station label."""
    key = _clean_name(name)
    low = key.lower()
    for frag, canon in RIVER_ALIASES.items():
        if frag in low:
            return canon
    return key


def river_from_station(station_name: str, sheet_river: str) -> str:
    """For multi-river WQMA sheets the waterbody is embedded in the station name."""
    s = str(station_name)
    m = re.match(r"\s*([A-Za-z0-9 .'-]*?(?:river|creek))(?:\s|$)", s, re.I)
    if m:
        cand = normalize_waterbody(m.group(1))
        if cand and cand != "UNKNOWN" and len(cand) > 3:
            return cand
    return sheet_river


def is_non_river(sheet_name: str) -> bool:
    key = sheet_name.strip().upper()
    return any(p in key for p in NON_RIVER_PATTERNS)


# ----------------------------------------------------------------------------
# Value parsing helpers
# ----------------------------------------------------------------------------
def parse_wq_value(raw):
    """Parse a worksheet cell into (value, status).

    status in {'ok', 'detection_limit', 'missing', 'invalid'}
    detection_limit -> value is the numeric part of a '<x' expression.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return np.nan, "missing"
    if isinstance(raw, (int, float)):
        return float(raw), "ok"
    s = str(raw).strip()
    if s == "" or s in {"nan", "NaN"}:
        return np.nan, "missing"
    up = s.upper()
    if "*" in s:
        return np.nan, "missing"
    if up in {"N/A", "NA", "-", "NONE", "AVERAGE", "MINIMUM", "MAXIMUM", "MIN", "MAX", "AVG"}:
        return np.nan, "missing"
    if "#REF!" in s or "#VALUE!" in s or "#N/A" in s:
        return np.nan, "invalid"
    limit = False
    if s.startswith("<") or s.startswith("<="):
        limit = True
        s = s.lstrip("<")
    s = s.replace(",", "")
    try:
        num = float(s)
    except ValueError:
        return np.nan, "invalid"
    return num, ("detection_limit" if limit else "ok")


def _row_strings(df_raw: pd.DataFrame, i: int) -> list[str]:
    """Row i as a list of stripped strings (NaN -> '').

    pandas 3.x keeps NaN as a float even after ``astype(str)`` on the new
    ``str`` dtype, so we normalise explicitly.
    """
    vals = df_raw.iloc[i].tolist()
    return ["" if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v).strip()
            for v in vals]


def cell_str(df_raw: pd.DataFrame, i: int, col) -> str:
    """Stripped string of cell (i, col); NaN/None -> ''."""
    if col is None or col >= df_raw.shape[1]:
        return ""
    v = df_raw.iloc[i, col]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return str(v).strip()


def find_header_row(df_raw: pd.DataFrame):
    """Locate the data header row and its column map.

    Returns ``(hdr_idx, month_cols, quarter_cols, colmap)`` where

    * ``month_cols``  maps column index -> 1..12  (January..December)
    * ``quarter_cols`` maps column index -> 1..4  (1st..4th Quarter)
    * ``colmap``      maps a normalised label -> column index

    The month/quarter labels and the "Region / Parameter / Stn. No. / Stn. ID"
    labels may live on *different* rows (they do in the 2026 workbooks), so the
    column-label search scans every row from the top down to the header row.
    """
    ncol = df_raw.shape[1]
    label_keys = {
        "region": {"region"},
        "parameter": {"parameter"},
        "stn. no.": {"stn. no.", "stn. no", "station no", "station no."},
        "stn_id": {"stn. id", "stn. id.", "station id", "station id.", "station"},
        "address": {"address"},
        "wqg": {"wqg", "wqg class c"},
    }
    for i in range(min(len(df_raw), 12)):
        row = _row_strings(df_raw, i)
        month_cols = {}
        quarter_cols = {}
        for c in range(ncol):
            v = row[c]
            low = v.lower()
            if not v:
                continue
            for mk, mi in MONTH_NAMES.items():
                if low.startswith(mk) and len(v) <= 12:
                    month_cols[c] = mi
                    break
            else:
                mq = re.match(r"^(\d)(?:st|nd|rd|th)?\s*(?:q|qtr|quarter)\b", low)
                if not mq:
                    mq = re.match(r"^q\s*(\d)$", low)
                if mq:
                    q = int(mq.group(1))
                    if 1 <= q <= 4:
                        quarter_cols[c] = q
        if month_cols or quarter_cols:
            colmap = {}
            for j in range(0, i + 1):
                r2 = _row_strings(df_raw, j)
                for c in range(ncol):
                    low = r2[c].strip().lower()
                    if not low:
                        continue
                    for key, keys in label_keys.items():
                        if low in keys and key not in colmap:
                            colmap[key] = c
            return i, month_cols, quarter_cols, colmap
    return None, None, None, None


def canonical_param(raw_param: str) -> str:
    """Canonical parameter key from a free-text parameter label."""
    if raw_param is None:
        return "UNKNOWN"
    s = str(raw_param).strip()
    low = s.lower()
    for pat, canon in PARAM_PATTERNS:
        if re.search(pat, low, flags=re.IGNORECASE):
            return canon
    return s


def param_display(canonical: str) -> str:
    return PARAM_META.get(canonical, {}).get("display", canonical)


def param_unit(canonical: str) -> str:
    return PARAM_META.get(canonical, {}).get("unit", "")


def param_kind(canonical: str) -> str:
    return PARAM_META.get(canonical, {}).get("kind", "other")


def param_orientation(canonical: str) -> str:
    return PARAM_META.get(canonical, {}).get("orientation", "high_bad")


def make_safe_filename(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name))
    out = re.sub(r"_+", "_", out).strip("_")
    return out or "unnamed"


# ----------------------------------------------------------------------------
# Coordinate parsing
# ----------------------------------------------------------------------------
def coords_in_philippines(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return False
    return (4.0 <= lat <= 21.5) and (116.0 <= lon <= 128.0)


def quarter_of(dt):
    return (dt.year, (dt.month - 1) // 3 + 1)
