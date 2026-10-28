"""
inspect_excel_workbooks.py
===========================
Stage 2 of the pipeline.

Reads *every* worksheet of *every* water-quality workbook in the repository,
parses the DENR "Summary Report of Water Quality" layout (which appears in
three variants: monthly, quarterly and a mixed month/quarter layout) and
writes a standardised long-format observation table:

    data/processed/observations_long.csv

with columns

    Source_File, Source_Sheet, Waterbody, River, Station_Name, Station_ID,
    Stn_No, Parameter, Parameter_Canonical, Unit, Parameter_Kind,
    Year, Month, Quarter, Date, Period_Type, Value, Value_Status, Region,
    Address, WQG, Waterbody_Type

Nothing is fabricated: every value is parsed from a real cell. Asterisks,
dashes and unparseable text become Value_Status != 'ok' with a NaN Value so
missing data can be audited.

Usage
-----
    python code/inspect_excel_workbooks.py
"""

from __future__ import annotations

import os
import re
import sys
import glob
import datetime as _dt

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()


def detect_year(raw: pd.DataFrame, hdr_idx: int, sheet: str):
    block = " ".join(" ".join(C._row_strings(raw, j))
                     for j in range(min(hdr_idx + 1, raw.shape[0])))
    ys = re.findall(r"\b(20\d{2})\b", block)
    if ys:
        return int(max(set(ys), key=ys.count))
    m = re.search(r"(20\d{2})", sheet)
    return int(m.group(1)) if m else None


def extract_workbook(path: str) -> list[dict]:
    rows = []
    xls = pd.ExcelFile(path)
    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        except Exception as exc:  # pragma: no cover
            print(f"  ! could not read sheet {sheet}: {exc}")
            continue
        if raw.shape[0] < 3:
            continue
        hdr_idx, month_cols, quarter_cols, colmap = C.find_header_row(raw)
        if hdr_idx is None:
            continue  # guideline / summary table (no month/quarter columns)
        if quarter_cols:
            # A quarterly (or mixed) sheet: the quarter columns are authoritative.
            val_cols = [(c, "quarter", q) for c, q in
                        sorted(quarter_cols.items(), key=lambda kv: kv[1])]
        else:
            val_cols = [(c, "month", m) for c, m in
                        sorted(month_cols.items(), key=lambda kv: kv[1])]
        if not val_cols:
            continue
        year = detect_year(raw, hdr_idx, sheet)
        if year is None:
            continue

        param_col = colmap.get("parameter")
        stn_col = colmap.get("stn_id")
        stnno_col = colmap.get("stn. no.")
        region_col = colmap.get("region")
        addr_col = colmap.get("address")
        wqg_col = colmap.get("wqg")

        sheet_river = C.normalize_river_name(sheet)
        non_river = C.is_non_river(sheet)

        current_param = None
        for i in range(hdr_idx + 1, raw.shape[0]):
            if param_col is not None:
                pc = C.cell_str(raw, i, param_col)
                if pc:
                    current_param = pc
            if current_param is None:
                continue
            if stn_col is None:
                continue
            stn = C.cell_str(raw, i, stn_col)
            if stn == "" or stn.lower() in {"nan", "#ref!"}:
                continue
            stn_no = None
            if stnno_col is not None:
                v = C.cell_str(raw, i, stnno_col)
                if v:
                    try:
                        stn_no = int(float(v))
                    except Exception:
                        stn_no = None
            region = C.cell_str(raw, i, region_col)
            address = C.cell_str(raw, i, addr_col)
            wqg = C.cell_str(raw, i, wqg_col)

            river = C.river_from_station(stn, sheet_river)
            canon = C.canonical_param(current_param)
            for c, ptype, pnum in val_cols:
                val, status = C.parse_wq_value(raw.iloc[i, c])
                if ptype == "month":
                    month, quarter = pnum, (pnum - 1) // 3 + 1
                else:
                    month, quarter = None, pnum
                rows.append({
                    "Source_File": os.path.basename(path),
                    "Source_Sheet": sheet,
                    "Waterbody": sheet_river,
                    "River": river,
                    "Station_Name": stn,
                    "Station_ID": f"{river}|{stn}",
                    "Stn_No": stn_no,
                    "Parameter": current_param,
                    "Parameter_Canonical": canon,
                    "Unit": C.param_unit(canon),
                    "Parameter_Kind": C.param_kind(canon),
                    "Year": year,
                    "Month": month,
                    "Quarter": quarter,
                    "Date": None,
                    "Period_Type": ptype,
                    "Value": val,
                    "Value_Status": status,
                    "Region": region,
                    "Address": address,
                    "WQG": wqg,
                    "Waterbody_Type": "non-river" if non_river else "river",
                })
    return rows


def main():
    print("=" * 80)
    print("STAGE 2  -  EXCEL WORKBOOK DISCOVERY & STANDARDISED EXTRACTION")
    print("=" * 80)
    all_rows = []
    workbook_report = []
    for fn in C.EXCEL_FILES:
        path = os.path.join(C.REPO_ROOT, fn)
        if not os.path.exists(path):
            print(f"  ! missing workbook: {fn}")
            continue
        t0 = _dt.datetime.now()
        xls = pd.ExcelFile(path)
        recs = extract_workbook(path)
        dt = (_dt.datetime.now() - t0).total_seconds()
        workbook_report.append({
            "Source_File": fn,
            "Size_Bytes": os.path.getsize(path),
            "Sheets": len(xls.sheet_names),
            "Sheet_List": "; ".join(xls.sheet_names),
            "Records_Parsed": len(recs),
            "Parse_Seconds": round(dt, 2),
        })
        all_rows.extend(recs)
        print(f"  {fn:32s} sheets={len(xls.sheet_names):2d} records={len(recs):6d} ({dt:.1f}s)")

    obs = pd.DataFrame(all_rows)
    # build a real date column
    def _date(r):
        if r["Period_Type"] == "month":
            return pd.Timestamp(int(r["Year"]), int(r["Month"]), 1)
        return pd.Timestamp(int(r["Year"]), 3 * int(r["Quarter"]) - 1, 15)
    obs["Date"] = obs.apply(_date, axis=1)
    obs = obs.sort_values(["River", "Station_Name", "Parameter_Canonical", "Date"]).reset_index(drop=True)

    out = os.path.join(C.PROCESSED_DIR, "observations_long.csv")
    obs.to_csv(out, index=False)
    print(f"\nStandardised long table written: {out}")
    print(f"rows={len(obs)}  rivers={obs['River'].nunique()}  "
          f"stations={obs['Station_Name'].nunique()}  "
          f"parameters={obs['Parameter_Canonical'].nunique()}")
    print("\nPeriod types:", obs["Period_Type"].value_counts().to_dict())

    rep = pd.DataFrame(workbook_report)
    rep.to_csv(os.path.join(C.RESULTS_DIR, "workbook_inventory.csv"), index=False)

    print("\nTop rivers by observation count:")
    print(obs["River"].value_counts().head(30).to_string())
    print("\nParameters:")
    print(obs["Parameter_Canonical"].value_counts().to_string())
    print("\nDONE.")


if __name__ == "__main__":
    main()
