# Lunaria — Session Handoff

**Last updated:** 2026-11-14  
**Working directory:** `/home/yass/lunaria`  
**Status:** analysis pipeline complete, dashboard/report written, tests passing; waiting on higher-resolution LROC/LOLA data for pad certification.

---

## 1. What this project is

A transparent, NASA-data-driven comparison of six candidate lunar landing sites:

| Site ID | Name | Coordinate |
|---|---|---|
| `shackleton_rim` | Shackleton Crater Rim | 89.9°S, 0.0°E |
| `nobile_connecting_ridge` | Nobile Crater Rim / Connecting Ridge | 84.2°S, 60.7°E |
| `von_karman` | Von Kármán Crater | 45.5°S, 177.6°E |
| `marius_hills` | Marius Hills | 14.0°N, 56.0°W |
| `vallis_schroteri` | Vallis Schröteri & Cobra Head | 23.5°N, 48.2°W |
| `apollo17` | Apollo 17 — Taurus-Littrow Valley | 20.2°N, 30.8°E |

The pipeline scores terrain, solar lighting, Earth visibility/comms, science, ISRU, thermal, safety and data maturity, then recommends a site and a DEM-screened pinpoint pad.

---

## 2. TL;DR for the next session

**Winner (balanced profile): Nobile Crater Rim / Connecting Ridge, 81.1/100.**  
**Runner-up: Apollo 17, 64.4/100.**  
**Pinpoint candidate:** **84.2005°S, 60.7373°E**, 115 m from the supplied coordinate, pad slope p90 **5.49°**, open sky >5° **88.3%**.

- Nobile wins **4 of 5** mission profiles. Apollo 17 wins the **low-risk crewed sortie** profile at **80.6** vs Nobile **80.1** — effectively a tie.
- Nobile's weaknesses: **63.0%** direct-to-Earth, **269 h** longest outage, relay mandatory; the 30 m/px LOLA DEM is too coarse for final hazard certification.
- Shackleton's supplied rim coordinate is **not** the best polar site: slope p90 **34.5°**, solar **49.6%**. Its "Peak of Eternal Light" is not at exactly 89.9°S, 0°E.
- Von Kármán is scientifically outstanding but has **0%** direct-to-Earth; relay mandatory.

**If the next session does only one thing:** request the Nobile **LROC NAC stereo DTM + orthophoto** at 1–2 m / 0.5–1 m per pixel for the 4×4 km AOI, then re-run the terrain certification on that pad.

---

## 3. Repo map

```
lunaria/
├── .env                        # NASA_API_KEY, gitignored, mode 600; never print
├── README.md                   # project overview / quick start
├── REPORT.md                   # full analysis, tables, caveats, LROC/LOLA request
├── HANDOFF.md                  # this file
├── config/
│   ├── sites.json              # six sites + DEM service/projection assignments
│   ├── criteria.json           # eight criteria, scales, methods, tiers
│   ├── profiles.json           # baseline + 4 mission weight sets
│   ├── curated_scores.json     # Tier C science/thermal/safety/data scores
│   └── sources.json            # 18-source provenance registry
├── scripts/
│   ├── common.py               # paths, .env, HTTP retry/redaction, CSV/JSON helpers
│   ├── lunar_geom.py           # projections, DEM samples, slope, horizon, PSR geometry
│   ├── fetch_terrain.py        # Moon Trek DEM/PSR/hillshade/basemap fetcher
│   ├── fetch_horizons.py       # NASA/JPL Horizons Sun/Earth fetcher
│   ├── fetch_nasa.py           # APOD + NASA Image Library + local preview cache
│   ├── build_tables.py         # sites, ephemeris summary, source registry, gaps, placeholders
│   ├── score_sites.py          # MCDA, profiles, Monte Carlo, GeoJSON, recommendation.json
│   └── build_dashboard.py      # writes web/data.js from processed outputs
├── data/
│   ├── raw/                    # cached NASA responses (APOD, images, Horizons, Trek)
│   ├── interim/                # ephemeris_samples.csv, site_elevations.json
│   └── processed/              # ranking, scores, sensitivity, gaps, geojson, recommendation
├── placeholders/               # header-only schemas for missing datasets
├── web/                        # static dashboard: index.html, styles.css, app.js, data.js
└── tests/test_pipeline.py      # 17 offline regression tests
```

---

## 4. How to run

```bash
cd /home/yass/lunaria

# Recompute terrain from cached Moon Trek samples (no network if cache is warm)
python3 scripts/fetch_terrain.py

# Recompute ephemeris summary (cached Horizons payloads)
python3 scripts/build_tables.py

# Recompute scores, ranking, Monte Carlo, recommendation
python3 scripts/score_sites.py

# Rebuild dashboard payload
python3 scripts/build_dashboard.py

# Tests
python3 -m unittest discover -s tests -v

# Dashboard
python3 -m http.server 8765 --directory web
# open http://127.0.0.1:8765/
```

`fetch_horizons.py` is the expensive network step (105,132 rows); the primary scenario is already cached. `fetch_nasa.py` is cheap but APOD is currently returning HTTP 500 on NASA's side; the script treats that as non-fatal.

---

## 5. Current results snapshot

### Baseline ranking (site mode)

| Rank | Site | Score | Top-1 | Solar | Earth >5° | Outage | Slope p90 | Relay |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Nobile Ridge | 81.07 | 99.96% | 71.8% | 63.0% | 269 h | 5.78° | Yes |
| 2 | Apollo 17 | 64.40 | 0.04% | 51.4% | 100% | 0 h | 6.61° | No |
| 3 | Marius Hills | 62.32 | 0.00% | 49.4% | 100% | 0 h | 5.53° | No |
| 4 | Shackleton | 60.21 | 0.00% | 49.6% | 92.8% | 113 h | 34.52° | Yes |
| 5 | Vallis Schröteri | 56.91 | 0.00% | 53.1% | 100% | 0 h | 11.16° | No |
| 6 | Von Kármán | 47.62 | 0.00% | 49.4% | 0% | 8,761 h | 0.76° | Yes |

### Profile winners

| Profile | Winner | Score |
|---|---|---:|
| Balanced polar base | Nobile Ridge | 81.1 |
| Polar ISRU priority | Nobile Ridge | 81.8 |
| Low-risk crewed sortie | Apollo 17 | 80.6 |
| Science / geology priority | Nobile Ridge | 83.3 |
| Communications first | Nobile Ridge | 79.9 |

### Pinpoint pads

| Site | Lat | Lon | Offset | Pad p90 | Open sky >5° |
|---|---:|---:|---:|---:|---:|
| Nobile Ridge | 84.2005°S | 60.7373°E | 115 m | 5.49° | 88.3% |
| Apollo 17 | 20.1975°N | 30.7981°E | 91 m | 8.93° | 100% |
| Marius Hills | 14.0023°N | 55.9991°W | 74 m | 5.20° | 100% |
| Shackleton | 89.9033°S | 4.0946°W | 235 m | 33.91° | 57.2% |
| Vallis Schröteri | 23.5014°N | 48.1957°W | 128 m | 16.54° | 100% |
| Von Kármán | 45.5007°S | 177.5990°E | 28 m | 0.76° | 100% |

---

## 6. Measured vs. judged

**Measured / documented (Tier A/B):**
- Sun and Earth topocentric geometry from Horizons; terrain shadowing from DEM horizon profiles.
- DEM elevation, slope, roughness, horizon statistics and pinpoint pad.
- PSR centroid/area proximity (approximate edge distance).
- Apollo 17 ground truth is Tier A for data maturity.

**Analyst judgment (Tier C):**
- Science value, thermal stability, crew safety, data maturity (except Apollo 17's data maturity).
- Non-polar ISRU scores use a documented rubric because there is no polar PSR access.

The sensitivity model perturbs Tier C scores at ±10 points (1σ) and Tier A/B at ±3 points. Do not present Tier C scores as measurements.

---

## 7. Data and provenance

- **Horizons:** `data/raw/horizons/`; summary in `data/processed/ephemeris_summary.csv`.
- **Moon Trek DEMs:** `data/raw/trek/*_samples_*.json`, `*_identify.json`, `*_meta.json`; summary in `data/processed/terrain_summary.csv`.
- **PSR catalogue:** `data/raw/trek/psr_sp.geojson`; summary in `data/processed/psr_proximity.csv`.
- **NASA Image Library:** `data/raw/nasa/images.csv` and `data/raw/nasa/images/*.json`; cached previews in `web/assets/nasa/`.
- **Sources:** `config/sources.json`, `data/processed/source_registry.csv`.
- **DEM products used:** LOLA south-pole 5 m/px, LOLA south-pole 30 m/px, LOLA global 256 ppd, LROC NAC 2 m/px (Marius), LROC NAC DTM 5 m/px (Apollo 17).

The NASA API key is only in `.env` (gitignored, mode 600). It is never written to outputs. HTTP error URLs are redacted by `common.redact_url()`.

---

## 8. Known issues / caveats

1. **APOD was intermittent (HTTP 500).** `fetch_nasa.py` treats it as non-fatal; a lunar-themed record was eventually cached at `data/raw/nasa/apod.json`. It is illustrative only, with no scoring dependency.
2. **Pinpoint pads are not certified.** They are selected by a DEM objective (50% open sky, 35% flatness, 15% proximity) and re-checked on a 500 m grid. Boulders and metre-scale scarps are unresolved.
3. **Horizon model is 5 km / 2 m eye height.** Terrain beyond 5 km and the 18.6-year libration cycle are not fully modelled.
4. **PSR edge is a centroid-and-area approximation**, not a polygon distance and not an ice detection.
5. **Relay-required is a screening threshold** (<99% of year with Earth >5°). No link budget was ingested.
6. **Nobile's DEM is 30 m/px**, not landing-hazard resolution. This is the main reason for the P0 NAC request.
7. **Apollo 17's pinpoint pad p90 (8.93°) is worse than its site p90 (6.61°)** because the pad objective favours horizon openness. If a mission prioritises slope over sky view, re-rank the pad candidates with a different objective.
8. **Vallis Schröteri's 118 m/px global DEM** is too coarse for its extreme relief; its terrain score is the least reliable of the non-polar sites.
9. **Image Library relevance** is imperfect; the script filters out Earth-observation/unrelated matches, but the remaining images are presentation context, not site-specific verification.
10. **APOD/Images API rate limits** are not an issue at current volumes; keep the 0.4 s sleep in `fetch_nasa.py`.

---

## 9. Immediate next steps (priority order)

1. **Request P0 LROC data for Nobile Ridge** (NAC stereo DTM + orthophoto, 4×4 km AOI centered 84.2°S, 60.7°E). This is the single highest-value action.
2. **Request P0 LROC/LOLA data for Von Kármán and Vallis Schröteri** (NAC DTM, LOLA 5 m, NAC ortho) to replace the 118 m/px global DEM.
3. **Ingest and validate P0 data** into `placeholders/lroc_nac_dtm.csv`, `lroc_nac_ortho.csv`, `lola_5m_dem.csv`; re-run `fetch_terrain.py` against the new DEM services or a local raster path.
4. **Re-certify the Nobile pad** on the NAC DTM: recompute slope p90, roughness, boulder density, and horizon at the exact pad; update `terrain_summary.csv` and `recommendation.json`.
5. **Add a relay link budget** (`placeholders/relay_link_budget.csv`) for Nobile/Shackleton/Von Kármán; replace `relay_required` with a coverage/latency result.
6. **Add Diviner thermal time series** (`placeholders/diviner_thermal.csv`) and replace the Tier C thermal score.
7. **Add LEND WEH and Mini-RF CPR** for the polar sites; replace the PSR-proximity proxy with a volatile-evidence score.
8. **Optional:** add a lander-specific hazard model (boulder size-frequency, slope vs. footpad, landing ellipse) and a Monte Carlo dispersion analysis.
9. **Commit the repo** after reviewing `git status`; currently everything is uncommitted.

---

## 10. Exact LROC/LOLA request

### Nobile Ridge (winner) — P0

- **LROC NAC stereo DTM:** 1–2 m/px, controlled, with vertical error map. AOI: **84.134–84.266°S, 60.047–61.353°E** (~4×4 km, center 84.200°S, 60.700°E).
- **LROC NAC orthophoto:** 0.5–1 m/px, radiometrically calibrated, orthorectified to the DTM. Same AOI.
- **Acceptance:** vertical error < 1 m (1σ); slope error < 2° at 5 m baseline; geolocation < 5 m; no interpolated holes > 2 pixels.

### Von Kármán — P0

- **LROC NAC stereo DTM:** 1–2 m/px. AOI: **45.434–45.566°S, 177.506–177.694°E**.
- **LOLA 5–20 m DEM:** 5 m/px clip + shot-count/error layer. Same AOI.
- **LROC NAC orthophoto:** 0.5–1 m/px. Same AOI.

### Vallis Schröteri — P0

- **LROC NAC stereo DTM:** 1–2 m/px. AOI: **23.434–23.566°N, 48.128–48.272°W**.
- **LOLA 5–20 m DEM:** 5 m/px clip + shot-count/error layer. Same AOI.
- **LROC NAC orthophoto:** 0.5–1 m/px. Same AOI.

### All six sites — P1

- Diviner thermal maps/time series at site scale over a full lunar day.
- LROC NAC orthophoto + DTM for pad certification where not already P0.
- Relay communications link budget (Nobile, Shackleton, Von Kármán first).

### Shackleton — P1

- LROC NAC DTM/ortho at 1–2 m/px to test a specific illuminated ridge near the rim. The supplied 89.9°S, 0°E coordinate is steep (p90 34.5°) and is not a certified pad.

---

## 11. Environment / security

- Working directory: `/home/yass/lunaria` (git repo, currently no commits from this session unless one was made after this file was written).
- Python: standard library only. No numpy/pandas/requests. `PIL`, ImageMagick and Firefox are available for optional image/testing work.
- NASA API key: `.env`, gitignored, mode 600. **Never print, commit, or paste it into a report.** The code redacts `api_key` from error URLs.
- Dashboard: static, local, no server required; `web/data.js` is generated.
- Tests: 17 passing with `python3 -m unittest discover -s tests -v`.

---

## 12. Open questions for the user

1. Is the mission a **sustained polar base** (Nobile) or a **short crewed sortie** (Apollo 17)? The ranking is sensitive to that choice only in the sortie profile.
2. Is a **relay architecture** acceptable for Nobile/Shackleton/Von Kármán? If not, only the near-side sites remain viable.
3. What lander class and footpad/clearance assumptions should be used for the hazard model? The current pad is not vehicle-specific.
4. Is **ISRU water ice** a hard requirement or a bonus? If hard, Nobile and Shackleton lead; if not, Apollo 17/Marius gain.
5. Do you want a **robotic precursor** recommendation (e.g., a small lander to certify the Nobile pad) or only a crewed site?

---

## 13. Suggested commit message

```
Add six-site lunar landing analysis, dashboard, report and tests

- NASA/JPL Horizons Sun/Earth ephemerides for six sites (105,132 samples)
- Moon Trek LOLA/LROC DEM terrain, slope, 5 km horizons and pinpoint pads
- MCDA with five mission profiles and 5,000-draw joint uncertainty model
- Nobile Ridge recommended at 81.1/100; Apollo 17 runner-up at 64.4
- Static dashboard, REPORT.md, HANDOFF.md, 17 offline tests
- 34 data gaps with placeholder schemas and P0 LROC/LOLA requests
```
