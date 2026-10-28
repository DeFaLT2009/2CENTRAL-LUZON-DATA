# Deliverables Index

**Pipeline version:** clz-forecast-v1.0 · **Date:** 2026-10-28

## 1. Data products

| File | What it is |
|---|---|
| `data/processed/observations_long.csv` | standardised long table, 109,598 rows |
| `data/processed/observations_monthly.csv` | monthly observations |
| `data/processed/observations_quarterly.csv` | quarterly aggregates (29,696 rows) |
| `data/processed/series_inventory.csv` | one row per river/station/parameter (2,095) |
| `data/station_registry/station_inventory.csv` | full station registry (346 rows) |
| `data/station_registry/verified_coordinates.csv` | deduplicated coordinate layer (101) |
| `data/station_registry/coordinate_sources.csv` | per-coordinate provenance |
| `data/station_registry/coordinate_conflicts.csv` | coordinate conflicts |
| `data/station_registry/duplicate_coordinates.csv` | shared-coordinate clusters (24) |
| `data/forecasts/future_four_quarter_forecasts.csv` | 3,012 forecasts, all required columns |
| `data/geojson/rivers_approximate.geojson` | approximate river geometry (labelled) |
| `data/geojson/stations_verified.geojson` | verified station points |
| `data/geojson/forecast_points_h1.geojson` | horizon-1 forecast points |

## 2. Results

| File | What it is |
|---|---|
| `results/workbook_inventory.csv` | per-workbook extraction summary |
| `results/data_quality_report.csv` | Stage-4 QC checks |
| `results/model_comparison.csv` | per-series per-model validation metrics + selection |
| `results/historical_backtest_predictions.csv` | out-of-sample backtest (final 4 quarters) |
| `results/forecast_reliability_report.csv` | forecast reliability / exceedance roll-up |
| `results/validation_report.csv` | Stage-11 integrity checks |
| `results/validation_summary.json` | validation summary |
| `results/gis_map_index.json` | 2-D map index + geometry disclaimer |
| `models/model_configurations/model_selection.json` | selected model per series |

## 3. Charts

| Folder | Contents |
|---|---|
| `figures/line/per_station/` | single station/parameter: observed + backtest + forecast (24) |
| `figures/line/multistation/` | river-wide station mean by parameter (72) |
| `figures/line/model_comparison/` | all four models + RMSE bars (1) |
| `figures/line/regional/` | Region III river mean per parameter (6) |
| `figures/2d/` | individual + combined chemical/physical/microbial GIS maps (14) |
| `figures/3d/` | hypothetical terrain + per-river 3-D views (13) |

## 4. Google Earth Pro

| File | Contents |
|---|---|
| `Google_Earth_Pro/kml/clz_rivers_stations_forecasts.kml` | rivers (approx), stations, forecast points, terrain mesh |
| `Google_Earth_Pro/kml/clz_rivers_stations_forecasts.kmz` | zipped KML for import |
| `Google_Earth_Pro/screenshots/` | 3-D view PNGs |

## 5. Documentation

| File | Contents |
|---|---|
| `documentation/README.md` | master overview + quick start |
| `documentation/Methodology.md` | full method, stage by stage |
| `documentation/Coordinate_Verification.md` | coordinate provenance & confidence |
| `documentation/Data_Quality_Report.md` | QC findings |
| `documentation/Validation_Report.md` | end-to-end validation evidence |
| `documentation/Deliverables_Index.md` | this file |

## 6. Provenance labels used throughout

| Label | Meaning |
|---|---|
| `observed` | real source measurement |
| `backtest` | out-of-sample model prediction on held-out quarters |
| `forecast` | generated future prediction (horizon 1–4) |
| `derived` | composite (station mean / regional mean) computed from observations |
| `APPROXIMATE` | river geometry joined from verified stations; not surveyed |
| `HYPOTHETICAL` | synthetic elevation surface; not surveyed, no bathymetry |
