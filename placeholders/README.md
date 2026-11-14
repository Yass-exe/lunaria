# Data placeholders

These CSV files exist so that missing datasets are explicit, reviewable and easy to fill. **They contain headers only. No rows are synthetic.** Do not populate them with guessed values; add real records with provenance.

The authoritative request list is `data/processed/data_gaps.csv`. Each gap has:

- `site_id`, `gap_id`, `dataset`, `priority` (P0–P3)
- `aoi` — area of interest, approximately 4×4 km around the site
- `desired_resolution` and `why`
- `request_spec` — what to ask the data provider for
- `request_from` — suggested provider/team
- `placeholder_file` — the schema to fill
- `acceptance` — test the delivered product must pass

## Schemas

| File | Dataset | Key fields |
|---|---|---|
| `lroc_nac_dtm.csv` | LROC NAC stereo DTM | `nac_pair_id`, `dtm_id`, `resolution_m`, `crs`, bbox, `vertical_error_m`, `url` |
| `lroc_nac_ortho.csv` | LROC NAC orthophoto | `nac_pair_id`, `ortho_id`, `resolution_m`, `incidence_deg`, `solar_azimuth_deg`, bbox, `url` |
| `lola_5m_dem.csv` | LOLA 5–20 m DEM | `product_id`, `resolution_m`, `epoch`, `crs`, bbox, `url` |
| `diviner_thermal.csv` | Diviner thermal maps/time series | `product_id`, `season`, `local_time_hr`, `temperature_k`, `uncertainty_k`, `resolution_m`, `url` |
| `lend_weh.csv` | LEND water-equivalent hydrogen | `product_id`, `weh_pct`, `uncertainty_pct`, `footprint_km`, `epoch`, `url` |
| `mini_rf_cpr.csv` | Mini-RF / Mini-SAR CPR | `product_id`, `cpr`, `s1`, `incidence_deg`, `resolution_m`, `url` |
| `relay_link_budget.csv` | Relay communications link budget | `relay_asset`, `orbit`, `data_rate_mbps`, `coverage_frac`, `worst_outage_h`, `latency_s` |
| `ground_truth.csv` | Landed/ground-truth measurements | `source`, `product_id`, lat/lon/elevation, `measurement`, `value`, `unit`, `url` |
| `artemis_iii_region_geometry.csv` | Official Artemis III region polygons | `region_id`, `region_name`, `geometry_wkt`, `crs`, `source_url`, `source_version` |
| `barker_ldem_inventory.csv` | Barker LOLA LDEM product identifiers and coverage | `requested_site_id`, `product_id`, `resolution_m`, `crs`, bbox, error and coverage |

## Fill procedure

1. Obtain the product from the provider in the `request_from` column (NASA LROC / LOLA / Diviner / LEND / Mini-RF teams, PDS Geosciences, or the mission communications team).
2. Add one row per product/site, with:
   - the real `product_id` / `dtm_id` / `ortho_id`,
   - the native `resolution_m` and `crs`,
   - the exact bounding box in degrees,
   - the source `url` (PDS node or project archive),
   - `status` = `delivered` or `validated`,
   - a short `notes` field describing processing or caveats.
3. Do not mix resolutions in one row. If a product has multiple tiles, add multiple rows.
4. Preserve the header exactly; downstream code uses these column names.
5. After filling a file, re-run the relevant ingest/certification step and update `data/processed/data_gaps.csv` status.

## Acceptance targets (from the gaps table)

- **NAC DTM:** vertical error < 1 m (1σ); slope error < 2° at 5 m baseline.
- **NAC ortho:** orthorectified to the DTM; geolocation < 5 m; no clouds (not applicable on the Moon) and no interpolation holes > 2 pixels.
- **LOLA DEM:** full AOI coverage; shot-count/error layer included; no interpolated holes > 2 pixels.
- **Diviner:** at least 8 local-time bins and a summer/winter pair.
- **LEND:** footprint ≤ 0.5° or better.
- **Mini-RF:** 75–150 m/px CPR with incidence angle and S1.
- **Relay:** coverage fraction and worst-case outage for the proposed architecture.

## Important

PSR proximity in `data/processed/psr_proximity.csv` is a centroid-and-area approximation, not an ice detection. Filling the LEND/Mini-RF placeholders is how that proxy gets replaced with actual volatile evidence.

## South-polar screen

The polar-first request ledger is `data/processed/polar_data_gaps.csv`. Its P0 AOI is generated from the current provisional seed and must be regenerated whenever the winner moves. The current request covers approximately 4×4 km around **85.4342°S, 10.5273°W**.

The following remain deliberately header-only:

- `barker_ldem_inventory.csv` until an exact 5 m product ID, error layer, shot-count layer, and valid/interpolated-pixel mask are supplied;
- `artemis_iii_region_geometry.csv` until a versioned authoritative polygon layer for all 13 NASA names is supplied;
- `lroc_nac_dtm.csv` and `lroc_nac_ortho.csv` until controlled products covering the provisional seed are delivered.

Do not substitute the seven-feature `Site01_ROIs_SP` catalogue layer for the official 13-region Artemis geometry, and do not treat full coverage in a server-resampled raster as native LOLA shot coverage.
