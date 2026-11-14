# Lunaria — South-Pole Session Handoff

**Last updated:** 2026-11-14<br>
**Branch:** `south-pole-screening`<br>
**Status:** complete cached pipeline, polar dashboard, reusable data, and regression suite; awaiting higher-resolution LROC/LOLA inputs.

## Result snapshot

- **Winner:** `polar-region-r167-c278`
- **Refined region WGM:** 0.614245 (61.42/100)
- **Provisional seed:** **85.4342216°S, 10.5272519°W**
- **Elevation/source:** 1,402.42 m; 148.4375 m/px server-resampled LOLA export
- **Seed metrics:** solar 48.51%; Earth visibility 95.08%; longest dark 15.75 d; local slope p90 7.94°; equivalent-area PSR edge 2.60 km
- **Sensitivity:** winner 44.4% top-1; runner-up 35.0% under 1,000 Dirichlet weight draws
- **Barker validation:** **not validated**, because exact ROI/LDEM/error/mask inputs are absent
- **Certification:** none; this is a provisional source-pixel seed, not a landing pad

## One command

```bash
cd /home/yass/lunaria
python3 scripts/build_polar.py
```

Expected runtime on the current machine: roughly two minutes. The command rebuilds the 290,364-cell screen, six refined regions, Sun/Earth benchmark, dashboard, compressed metrics, and integrity manifest.

Tests:

```bash
python3 -B -m unittest discover -s tests -v
```

Dashboard:

```bash
python3 -m http.server 8765 --directory web
# http://127.0.0.1:8765/
```

## Important implementation facts

1. The ephemeris uses Horizons sub-solar/sub-Earth body-fixed coordinates **and range**. Range is required to correct Earth direction for lunar-surface parallax; omitting it caused a 0.246° elevation error.
2. Stage one uses the maximum source elevation as each 1 km observer. This is an explicitly optimistic ridge screen and is stored as `observer_elevation: max` in the manifest.
3. Stage two recomputes horizons for all ~148 m pixels inside the six shortlisted clusters before selecting a provisional seed.
4. `config/polar_scoring.json` is the scoring source of truth. Longest-dark utility uses 30 days and sunlight continuity is report-only.
5. `psr_edge_km` subtracts an equivalent-circle radius derived from catalogue area. It is no longer mislabeled centroid distance, but it is still not polygon distance or ice evidence.
6. Raster-valid coverage is not native LOLA shot coverage and is not weighted.
7. The authoritative Artemis III region geometry remains unavailable; `placeholders/artemis_iii_region_geometry.csv` must stay empty until sourced.
8. The NASA key remains only in gitignored `.env`. Moon Trek and Horizons requests do not receive it.

## Main outputs

- `data/processed/polar_recommendation.json`
- `data/processed/polar_refined_region_ranking.csv`
- `data/processed/polar_candidate_regions.geojson`
- `data/processed/polar_candidate_timeseries.csv`
- `data/processed/polar_cell_metrics.csv.gz`
- `data/processed/polar_terrain_1km.tif`
- `data/processed/polar_illumination_1km.tif`
- `data/processed/polar_benchmark.json`
- `data/processed/polar_data_gaps.csv`
- `data/processed/polar_data_manifest.json`
- `web/` — map layers, normalized weight sliders, and six-hour candidate status

Uncompressed `polar_cell_metrics.csv` and `polar_cell_scores.csv` are reproducible working files and gitignored. The previous six-site report/dashboard is preserved under `archive/six-site-analysis/`. Do not pop or drop the existing parked stash unless the user explicitly requests it.

## Exact data request for the next session

AOI around **85.4342°S, 10.5273°W**, approximately 4×4 km:

- latitude **-85.500177 to -85.368266**
- longitude **-11.355805 to -9.698699**

Request:

1. Barker/LOLA **5 m LDEM**, exact product/site ID, error layer, shot count, and valid/interpolated-pixel mask.
2. Controlled **LROC NAC stereo DTM**, 1–2 m/px, source image IDs, control report, and vertical-error map.
3. Matching **LROC NAC orthophoto**, 0.5–1 m/px, radiometrically calibrated and tied to the DTM.
4. The official versioned polygons for all 13 Artemis III candidate regions.

After delivery, ingest without interpolating invalid Barker cells, recompute fine horizons/slope, assess a vehicle-specific landing ellipse, and rerun `scripts/build_polar.py` before changing the recommendation.
