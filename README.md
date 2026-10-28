# 2CENTRAL-LUZON-DATA — Central Luzon (Region III) Water-Quality Forecast Study

Reproducible audit-and-rebuild of the legacy `Future-predictor8.py` into a
12-stage pipeline: workbook extraction → station/river discovery → coordinate
verification → quarterly data prep → chronological model validation → four-
quarter forecasts → mandatory line graphs → forecast-driven 2-D GIS maps →
(hypothetical) 3-D terrain → Google Earth KML/KMZ → end-to-end validation.

**Scope:** Central Luzon Region III broadly — not limited to Rio Chico, Lucong
or six predefined stations. Rivers and stations are discovered dynamically.

## Documentation

Start at **`documentation/README.md`** (quick start + headline results), then:

- `documentation/Methodology.md` — full stage-by-stage method
- `documentation/Coordinate_Verification.md` — coordinate provenance & confidence
- `documentation/Data_Quality_Report.md` — QC findings
- `documentation/Validation_Report.md` — end-to-end validation (27/27 passed)
- `documentation/Deliverables_Index.md` — every deliverable file

## Quick start

```bash
cd 2CENTRAL-LUZON-DATA
for s in inspect_excel_workbooks discover_and_verify_stations data_preparation \
         train_and_validate generate_forecasts line_graphs gis_2d_maps \
         terrain_3d_river_map kml_export validate_pipeline; do
  python code/$s.py
done
```

All stages are idempotent and write to fixed output directories.

## Headline results (2026-10-28)

- 10 source workbooks (2017–2026) → 109,598 raw observation rows → 29,696 quarterly rows
- 2,095 river/station/parameter series; 753 eligible (≥20 quarterly observations)
- 3,012 four-quarter forecasts; 1,680 mapping-eligible (verified coordinates)
- 19 study rivers with resolved coordinates + observations
- 107 verified coordinate records from 2 repository sources; 3 corrected from placeholders
- 4 competing models (Naive, Seasonal Naive, ARIMA, LSTM) under expanding-window validation
- 103 line graphs, 14 2-D GIS maps, 13 3-D views, KML/KMZ for Google Earth Pro
- **27 / 27 end-to-end validation checks passed**

## Honesty guarantees

- Repository coordinates are used first and never silently overwritten.
- No measurements, coordinates, forecasts, graph points, river geometry or
  bathymetry are fabricated.
- River geometry is labelled **APPROXIMATE**; the 3-D terrain is labelled
  **HYPOTHETICAL** (no DEM or bathymetry available).
- Observations, backtest predictions, future forecasts and derived composites
  are kept visually and semantically distinct.
