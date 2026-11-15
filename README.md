# Lunaria

A NASA-data-driven screening of the lunar south pole from **80–90°S**. Lunaria evaluates 290,364 one-kilometre cells, clusters high-suitability regions, recomputes shortlisted terrain and visibility on the ~148 m source raster, and reports an exact **provisional** seed for higher-resolution investigation.

**Current screening winner:** `polar-region-r167-c278`, **60.15/100** weighted geometric score.<br>
**Provisional seed:** **85.4342°S, 10.5273°W**, elevation 1,402 m.<br>
**Important:** this is not a certified landing pad or hazard map.

## Run it

```bash
cd /home/yass/lunaria
python3 -m pip install -r requirements-polar.txt
python3 scripts/build_polar.py
```

The complete cached build takes about two minutes on the current machine. It rebuilds illumination/comms, scores and clusters the full cap, refines six regions, checks Sun and Earth geometry against JPL Horizons, generates the dashboard, compresses reusable metrics, and writes checksums.

View the dashboard:

```bash
python3 -m http.server 8765
# open http://127.0.0.1:8765/web/
```

Run the offline suite:

```bash
python3 -B -m unittest discover -s tests -v
```

## What the result says

- The winning region's provisional seed has **48.5%** two-year solar illumination, **95.1%** direct Earth visibility above its terrain horizon, a **15.75-day** longest sampled dark run, ~**7.94°** local slope p90 at the available scale, and an approximate PSR edge **2.60 km** away.
- The win is not decisive: it receives **39.0%** of top-rank outcomes under 1,000 Dirichlet weight draws; the runner-up receives **38.5%**.
- The exact Artemis III region name is deliberately not assigned because authoritative 13-region polygons were not available.
- Barker Site 01/04/07/11 validation is **FAIL/BLOCKED** because the exact 5 m LDEMs, error layers, and valid-pixel masks are missing.

## Two-stage method

1. **Full-cap screen:** a 1 km grid uses the highest ~148 m source pixel in each cell as an optimistic ridge observer, terrain horizons to 60 km, and 2,925 six-hour samples from 2024-01-01 through 2026-01-01.
2. **Shortlist refinement:** every source pixel inside the six baseline clusters gets a new fine-raster horizon and score. The best source pixel becomes a provisional seed—not a landing pad.

The headline score is a weighted geometric mean of solar power, Earth visibility, terrain safety, approximate PSR access, a neutral science placeholder, and a thermal proxy. Science is fixed at 0.5 until an independent geology/spectral layer exists, so terrain slope is not double-counted. Sunlight continuity is reported but not weighted because it is correlated with illumination and dark-period metrics. Raster-valid coverage is displayed separately and is not native LOLA shot coverage.

## Key files

- [`REPORT.md`](REPORT.md) — result, ranking, method, validation, caveats, and data request
- [`HANDOFF.md`](HANDOFF.md) — exact state and next-session instructions
- `web/` — polar dashboard with map layers, normalized weight sliders, and six-hour date status
- `data/processed/polar_recommendation.json` — machine-readable verdict
- `data/processed/polar_refined_region_ranking.csv` — final six-region ranking
- `data/processed/polar_candidate_regions.geojson` — stage-one cluster geometry
- `data/processed/polar_candidate_timeseries.csv` — date-aware Sun/Earth status
- `data/processed/polar_cell_metrics.csv.gz` — compressed reusable measurements for 290,364 cells
- `data/processed/polar_data_manifest.json` — SHA-256 integrity manifest
- `data/processed/polar_data_gaps.csv` — exact missing-data requests and acceptance tests

The previous six-site analysis is preserved under [`archive/six-site-analysis/`](archive/six-site-analysis/). The NASA API key remains only in gitignored `.env` and is not sent to public Moon Trek or Horizons endpoints.
