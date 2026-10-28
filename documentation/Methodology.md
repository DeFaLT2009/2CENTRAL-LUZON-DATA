# Methodology

**Pipeline version:** clz-forecast-v1.0 · **Date:** 2026-10-28

## Stage 1 — Source audit

The legacy `Future-predictor8.py` was read directly from the repository (not
assumed to run) before anything was changed. It is a monthly LSTM forecaster
with a hard-coded `STATION_COORDS` table of six stations, three of which are
Lucong River rows that are the **only** non-zero Lucong coordinates anywhere in
the repository. Those three were preserved verbatim and later used to correct
the three `0,0` Lucong placeholders in the coordinate CSV.

## Stage 2 — Station & river discovery

`code/inspect_excel_workbooks.py` reads all ten workbooks, auto-detects the
header row (quarter-aware: some 2025/2026 sheets are quarter-only), parses the
monthly matrix and emits a standardised long table
(`data/processed/observations_long.csv`, 109,598 rows). River and station
names are normalised via `clz_common.py`; generic/statistical rows
(AVERAGE, MAXIMUM, MINIMUM, STANDARD, Annual 2025, Water Quality Statistical
Report, …) are dropped as non-parameters.

## Stage 3 — Coordinate verification (repository first)

`code/discover_and_verify_stations.py` loads:
- `sampling station coords.xlsx - merged.csv` (102 rows; the waterbody name is
  in the `layer` column — `WB_Name` is ~100/102 NaN);
- `Future-predictor8.py` `STATION_COORDS`.

It applies `core_station()` (strips address blocks, normalises punctuation,
maps `STATION n` / `300 m AWAY FROM STATION n` → `MOUTH STATION n`, resolves
`STATION_ALIASES` transitively), `river_canonical()` and river-parent mapping,
then flags `0,0` placeholders, lat/lon swaps and out-of-Philippines values.
Only unresolved / ambiguous / conflicting stations were researched online.

## Stage 4 — Data preparation & QC

`code/data_preparation.py`:
- filters to `Value_Status ∈ {ok, detection_limit}` and a whitelist of
  water-quality parameters;
- merges the station registry on a **case-insensitive** `River + station` key
  so workbook names ("Angeles River 1") join to canonical registry names
  ("ANGELES RIVER 1");
- aggregates monthly records to quarters by mean, keeping `N_Months`;
- keeps direct quarterly-report values flagged `quarterly_report`;
- writes `results/data_quality_report.csv`.

## Stage 5 — Chronological model validation

`code/train_and_validate.py` compares four models on every eligible series
(≥20 quarterly observations, 722 series):

| Model | Definition |
|---|---|
| Naive | repeat the last observed quarter |
| SeasonalNaive | repeat the last annual (4-quarter) cycle |
| ARIMA | statsmodels ARIMA, best AIC over `(1,1,1),(2,1,1),(1,1,2),(2,1,2),(1,0,1)` |
| LSTM | compact torch LSTM (seq=8, hidden=24, 35 epochs) |

Validation uses a strictly chronological **expanding-window** protocol with
multiple origins (step = 1 quarter, up to 6 origins). No shuffle, no leakage.
Microbial counts (Fecal / Total Coliform) are modelled on `log1p` and
back-transformed exactly once. The model with the lowest mean validation RMSE
is selected per series; its out-of-sample prediction on the final four quarters
is saved as the backtest.

## Stage 6 — Four-quarter forecasts

`code/generate_forecasts.py` refits each selected model on **all** data up to
that series' own last observed quarter (per-series forecast origins) and
produces the next four quarterly forecasts. Each row carries the full required
column set including `Training_Period`, `Observation_Count`, `Model_Version`,
`Forecast_Generation_Timestamp`, `Reliability_Flag` and
`Mapping_Eligibility`. Intervals: ARIMA uses model confidence intervals; other
models use a documented `empirical_rmse_band` (±1.96 × validation RMSE).

## Stage 7 — Mandatory line graphs

`code/line_graphs.py` renders four families, each combining observed history
(solid), backtest predictions (dashed) and future forecasts (dotted, with the
interval band):
- **per-station** (24 figures) — single station/parameter detail;
- **multi-station** (71 figures) — river-wide station mean by parameter;
- **model-comparison** (1 figure) — all models on one backtest window + RMSE bars;
- **regional** (6 figures) — Region III river mean per parameter + forecast.

## Stage 8 — Forecast-driven 2-D GIS maps

`code/gis_2d_maps.py` builds forecast-driven maps from verified coordinates:
- **individual** chemical maps (DO, BOD, NH3, NO3-N, PO4-P, Cl);
- **individual** physical maps (TSS, Temp, pH, Color);
- **microbial** maps (Fecal / Total Coliform, log scale);
- **combined** chemical + all-parameter Class-C exceedance maps.

River geometry is **approximate** — verified stations of each river joined in
longitude order, explicitly labelled `APPROXIMATE - NOT SURVEYED GEOMETRY`.

## Stage 9 — 3-D terrain (hypothetical)

`code/terrain_3d_river_map.py` builds a synthetic elevation surface because no
DEM is available and geospatial hosts are unreachable. It is labelled
`HYPOTHETICAL - NOT SURVEYED ELEVATION OR BATHYMETRY`. No bathymetry or
water-depth claim is made anywhere.

## Stage 10 — Google Earth Pro KML / KMZ

`code/kml_export.py` exports the approximate rivers, verified stations
(provenance in the placemark description), forecast points (Pass/Fail styled)
and the hypothetical terrain mesh as `.kml` + `.kmz`.

## Stage 11 — End-to-end validation

`code/validate_pipeline.py` runs 27 integrity checks covering input presence,
forecast traceability, chronological ordering, coordinate provenance, model
integrity, interval validity, artifact existence and data quality. Result:
**27 / 27 passed** (`results/validation_summary.json`).

## Distinguishing data classes

| Class | Colour/style in figures | Provenance |
|---|---|---|
| Observations | solid grey/parameter colour | workbook source rows |
| Backtest predictions | dashed red | out-of-sample, final 4 quarters |
| Future forecasts | dotted blue + band | generated, horizon 1–4 |
| Derived composites | station mean, regional mean | derived from observations |
| Hypothetical geometry | terrain/river overlay | synthetic, labelled |

## Known limitations

- River geometry and terrain are approximate/hypothetical (no DEM, no
  shapefiles, geospatial hosts unreachable).
- Some stations (mouth sections, coastal/beach sites, generic "near …" labels)
  have no coordinate source and are reported as `unresolved`.
- Naive / Seasonal-Naive win many series because quarterly environmental data
  is noisy; this is a real finding, not a defect.
