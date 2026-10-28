# Central Luzon (Region III) Water-Quality Forecast Study

A reproducible audit-and-rebuild of the legacy `Future-predictor8.py` into a
12-stage pipeline that ingests the DENR-EMB Region 3 monitoring workbooks
(2017–2026), verifies station coordinates, prepares quarterly water-quality
series, forecasts four quarters ahead with four competing models, and produces
traceable line graphs, 2-D GIS maps, a (hypothetical) 3-D terrain view, Google
Earth KML/KMZ, and an end-to-end validation report.

**Author / date:** Arena agent · 2026-10-28
**Scope:** Central Luzon Region III broadly — **not** restricted to Rio Chico,
Lucong, or six predefined stations. Rivers and stations are discovered
dynamically from the workbooks.

---

## 1. Quick start

```bash
cd 2CENTRAL-LUZON-DATA
/home/user/.venv/bin/python code/inspect_excel_workbooks.py     # Stage 2 - extract
/home/user/.venv/bin/python code/discover_and_verify_stations.py # Stage 3 - coordinates
/home/user/.venv/bin/python code/data_preparation.py             # Stage 4 - quarterly + QC
/home/user/.venv/bin/python code/train_and_validate.py           # Stage 5 - model comparison
/home/user/.venv/bin/python code/generate_forecasts.py           # Stage 6 - 4-quarter forecasts
/home/user/.venv/bin/python code/line_graphs.py                  # Stage 7 - mandatory line graphs
/home/user/.venv/bin/python code/gis_2d_maps.py                  # Stage 8 - 2-D GIS maps
/home/user/.venv/bin/python code/terrain_3d_river_map.py         # Stage 9 - 3-D (hypothetical)
/home/user/.venv/bin/python code/kml_export.py                   # Stage 10 - KML / KMZ
/home/user/.venv/bin/python code/validate_pipeline.py            # Stage 11 - validation
```

Stages are idempotent and can be re-run individually; each writes to a fixed
output directory.

## 2. Directory layout

| Path | Contents |
|---|---|
| `code/` | One script per pipeline stage + shared `clz_common.py` |
| `data/processed/` | `observations_long.csv`, `observations_monthly.csv`, `observations_quarterly.csv`, `series_inventory.csv` |
| `data/station_registry/` | `station_inventory.csv`, `verified_coordinates.csv`, `coordinate_sources.csv`, `coordinate_conflicts.csv`, `duplicate_coordinates.csv` |
| `data/forecasts/` | `future_four_quarter_forecasts.csv` (all required columns) |
| `data/geojson/` | `rivers_approximate.geojson`, `stations_verified.geojson`, `forecast_points_h1.geojson`, hypothetical terrain grid |
| `results/` | `model_comparison.csv`, `historical_backtest_predictions.csv`, `data_quality_report.csv`, `forecast_reliability_report.csv`, `validation_report.csv`, `validation_summary.json`, `workbook_inventory.csv`, `gis_map_index.json` |
| `figures/line/` | per-station, multi-station, model-comparison and regional line graphs |
| `figures/2d/` | individual + combined chemical/physical/microbial GIS maps |
| `figures/3d/` | hypothetical terrain + per-river 3-D views |
| `Google_Earth_Pro/` | `kml/clz_rivers_stations_forecasts.kml` / `.kmz`, `screenshots/` |
| `models/model_configurations/` | `model_selection.json` |
| `documentation/` | this file + Methodology, Data-Quality, Validation and Deliverables docs |

## 3. Headline results

| Metric | Value |
|---|---|
| Source workbooks | 10 (2017–2025, Jan–Jun 2026) |
| Raw observation rows | 109,598 |
| Rows with usable values | 63,007 |
| Missing / invalid / detection-limit | 44,394 / 1,963 / 1,894 |
| Distinct parameters (modelled) | 10 |
| Quarterly rows (aggregated) | 29,696 |
| Distinct river/station/parameter series | 2,095 |
| Eligible series (≥20 quarterly obs) | 753 |
| Forecast rows (4 quarters × 753 series) | 3,012 |
| Mapping-eligible forecasts (have coordinates) | 1,680 |
| Verified coordinate records | 107 (2 source files) |
| Corrected from placeholder | 3 |
| Waterbodies / coordinate stations | 38 / 62 |
| Study rivers with resolved coordinates + observations | 19 |
| River geometry lines (approximate) | 17 |
| Rivers covered by forecasts | 31 |
| Models compared | Naive, Seasonal Naive, ARIMA, LSTM |
| Model selection (753 series) | ARIMA 249 · Naive 218 · LSTM 149 · SeasonalNaive 137 |
| Line graphs / 2-D maps / 3-D views | 103 / 14 / 13 |
| Validation checks passed | 27 / 27 |

## 4. Golden rules enforced

1. **Repository coordinates first** — never silently overwritten; every accepted
   coordinate carries a provenance record.
2. **No fabrication** — no invented measurements, coordinates, forecasts, graph
   points, river geometry or bathymetry.
3. **Traceability** — every forecast row references its source station,
   training period, observation count, selected model and coordinate provenance.
4. **Distinct artefact classes** — observations, backtest predictions, future
   forecasts, derived composites and hypothetical geometry are never mixed or
   mislabelled.
5. **Honest coverage** — geographic/monitoring coverage is reported as measured,
   not claimed to be complete.

See `documentation/Methodology.md` for the full method and
`documentation/Validation_Report.md` for the integrity evidence.
