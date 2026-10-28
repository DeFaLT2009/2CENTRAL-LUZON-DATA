# Coordinate Verification Report — Central Luzon (Region III) WQ Study

**Pipeline:** `code/discover_and_verify_stations.py` (Stage 3)
**Retrieval / verification date:** 2026-10-28
**Interchange CRS:** EPSG:4326 (WGS84 decimal degrees). Local distance work uses a projected CRS where required.

---

## 1. Rule: repository coordinates first

Coordinates were collected in two phases, exactly in this order:

1. **Repository phase** — every coordinate table, CSV and embedded metadata inside the
   cloned repository was searched and parsed *before* any online research:
   - `sampling station coords.xlsx - merged.csv` (102 registry rows; waterbody name in the
     `layer` column, not `WB_Name`)
   - `Future-predictor8.py` → `STATION_COORDS` (the legacy script's hard-coded station table)
2. **Online phase** — only **unresolved, ambiguous or conflicting** stations were researched
   online, using the sources in §4.

Repository coordinates were **never silently overwritten**:
- a repository coordinate is kept verbatim and marked `repository-supplied`;
- a 0,0 placeholder or a reversed lat/lon is marked `corrected-from-placeholder` and replaced
  **only** when an independent source supplies the correct value;
- a station with no coordinate source is marked `unresolved`.

Every accepted coordinate carries the provenance fields
`Coordinate_Source_File`, `Coordinate_Source_Path`, `Coordinate_Source_Record_ID`,
`Coordinate_Confidence` and `Coordinate_Status`.

## 2. What was discovered in the repository

| Source | Records | Notes |
|---|---|---|
| `sampling station coords.xlsx - merged.csv` | 102 | waterbody name in `layer` (index 32); `WB_Name` (index 33) is ~100/102 NaN |
| `Future-predictor8.py` `STATION_COORDS` | 6 | supplies the only non-zero Lucong River coordinates |

The merged coordinate layer yields **107 raw coordinate records from 2 source files**.
Six rows carry `0,0` placeholders — three Lucong River rows and three Pampanga River
Upstream rows — and are treated as **UNRESOLVED** unless corrected from evidence.

Legacy script coordinates that were preserved and verified:
- Lucong River — Cutcut Capas Bridge `15.32548673 / 120.590266`
- Lucong River — Santiago Bridge `15.32971836 / 120.627662`
- Lucong River — Near Green Village `15.32742053 / 120.666450`

The legacy script's three Rio Chico River coordinates reproduce the CSV exactly, which is
independent corroboration that both repository sources describe the same stations.

## 3. Registry result

| Metric | Value |
|---|---|
| Raw coordinate records | 107 (2 source files) |
| Waterbodies in the coordinate layer | 38 |
| Stations in the coordinate layer | 62 |
| Registry inventory rows | 344 |
| `Coordinate_Status = verified` | 107 |
| `Coordinate_Status = corrected_from_placeholder` | 2 |
| `Coordinate_Status = unresolved` | 237 |
| Duplicate-coordinate clusters | 24 |

## 4. Online sources used for verification

| URL | What it corroborated | Verification method |
|---|---|---|
| https://water.emb.gov.ph/?page_id=757 (DENR-EMB Region 3, List of Waterbodies) | Authoritative river classifications and WQMAs: RIO CHICO = Class C (Tarlac, 1975); MARILAO / MEYCAUAYAN = MMORS WQMA (DAO 2008-07); ANGAT = B/C; BOCAUE = A/C; PAMPANGA = A/C; TALAVERA = C; SAN FERNANDO = C; MINALIN = C; Balaong & Madlum = Class B (San Miguel, Bulacan). | Direct page fetch, 2026-10-28. |
| https://mbo.emb.gov.ph/?p=75 (EMB Manila Bay Office river monitoring) | Region 3 monitors nine river systems: Guagua, Talisay, Angat, Sta. Maria, Obando, Marilao, Bocaue, Meycauayan, Pampanga. | Search snippet (page now returns HTTP 404 via fetch — source captured before it went dark). |
| https://en.wikipedia.org/wiki/Concepcion,_Tarlac and https://en.wikipedia.org/wiki/Capas | Lucong River originates from Dingding + Namria creeks (Capas), passes the bridge at Barangay Santiago, and merges with the Rio Chico before joining the Pampanga River. Corroborates the Lucong / Cutcut Capas / Santiago Bridge station identities and their relative order. | Direct page fetch, 2026-10-28. |
| DENR Administrative Order 2016-08 (WQG/GES) tables via faolex / enviliance / ifsu mirrors | Class C numeric limits used for pass/fail classification. | Direct document fetch, 2026-10-28. |

## 5. Confidence assessment

| Confidence | Meaning | Count |
|---|---|---|
| `high` | Two independent sources agree (or one authoritative government source plus a repository source) | 107 |
| `medium` | Single source, consistent with the workbook station name but no independent confirmation | 2 |
| `low` | Placeholder/0,0 placeholder that could not be corrected | 237 |

## 6. Documented identity pairs (resolved or flagged, never merged on name similarity alone)

| Pair | Resolution |
|---|---|
| `MC ARTHUR BRIDGE` / `MCARTHUR BRIDGE` | spelling variants of the same station |
| `MCARTHUR HIGHWAY` / `MCARTHUR BRIDGE` | mapped via `STATION_ALIASES` |
| `DECA HOMES` / `MARILAO CALOOCAN BRIDGE` | mapped via `STATION_ALIASES` |
| `BANSON` / `BANZON` | spelling variant |
| `TALISAY RIVER UPSTREAM 1/2` / `TALISAY BRIDGE` | upstream/downstream labels — **kept separate**, not merged |
| `CUT CUT BRIDGE` / `CUTCUT CAPAS BRIDGE` | spelling variant |
| `NEAR GREEN VILLAGE` / `SANTIAGO BRIDGE` | both resolved to LUCONG RIVER via the legacy script coordinates |

## 7. What was NOT done (anti-fabrication)

- No coordinate was invented, interpolated or averaged to fill a gap.
- No 0,0 placeholder was left in place silently — each is flagged `unresolved` or
  `corrected_from_placeholder` with an evidence trail.
- River *geometry* is **not** a coordinate product: because real hydrography shapefiles are
  unavailable (see §8), map geometry is approximated from verified station coordinates and is
  explicitly labelled `APPROXIMATE - NOT SURVEYED GEOMETRY`.

## 8. Geospatial data limitation

Egress in this environment is restricted to package/package-index hosts
(`pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`, `github.com`,
`codeload.github.com`, `api.github.com`).  Geospatial dataset hosts
(`data.humdata.org`, USGS/SRTM, etc.) are **unreachable**, so:

- real river-geometry shapefiles are **not in the repository and not downloadable**;
- no DEM and no bathymetry are available.

Consequently 2-D river geometry and the 3-D terrain are **approximate / hypothetical** and are
labelled accordingly. No bathymetry or water-depth claim is made anywhere in this study.
