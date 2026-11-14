# Lunaria

A transparent, NASA-data-driven comparison of six candidate lunar landing sites — built to recommend a first landing site and a pinpoint pad, while keeping measured evidence separate from analyst judgment.

**Current recommendation: Nobile Crater Rim / Connecting Ridge (84.2°S, 60.7°E), 81.1/100.**  
**Pinpoint candidate: 84.2005°S, 60.7373°E** — 115 m from the supplied coordinate, pad slope p90 5.49°.  
**Runner-up: Apollo 17 — Taurus-Littrow Valley, 64.4/100** (best low-risk crewed sortie).

> Screening and decision support only. This is not a flight-certified landing site or a hazard map.

## What it does

- Fetches **NASA/JPL Horizons** topocentric Sun and Earth geometry for 2026-11-14 → 2027-11-14.
- Samples **NASA Moon Trek / LRO LOLA and LROC** DEMs for terrain, slope, roughness, 5 km horizon profiles and a DEM-screened pinpoint pad.
- Scores eight criteria: solar illumination, Earth link, terrain trafficability, ISRU/water-ice access, science, thermal, crew safety and data maturity.
- Runs five mission profiles plus a **5,000-draw joint weight-and-score uncertainty model**.
- Tracks **34 missing datasets** with AOIs, request specifications, acceptance tests and header-only placeholder files.

## Quick start

```bash
cd /home/yass/lunaria

# Rebuild from cached NASA data
python3 scripts/build_tables.py
python3 scripts/score_sites.py
python3 scripts/build_dashboard.py

# Tests
python3 -m unittest discover -s tests -v

# Dashboard
python3 -m http.server 8765 --directory web
# open http://127.0.0.1:8765/
```

Network refresh (optional; cached data already exists):

```bash
python3 scripts/fetch_terrain.py
python3 scripts/fetch_horizons.py
python3 scripts/fetch_nasa.py
```

The NASA API key is read from `.env` (`NASA_API_KEY=...`), which is gitignored and never written to outputs.

## Read more

- **[REPORT.md](REPORT.md)** — full analysis, ranking tables, per-site assessments, method, caveats and the exact LROC/LOLA request.
- **[HANDOFF.md](HANDOFF.md)** — next-session status, commands, open questions and prioritized next steps.
- **`web/index.html`** — self-contained static dashboard (works from the filesystem).

## Key results

| Rank | Site | Score | Solar | Earth >5° | Slope p90 | Relay |
|---:|---|---:|---:|---:|---:|---|
| 1 | Nobile Ridge | 81.07 | 71.8% | 63.0% | 5.78° | Yes |
| 2 | Apollo 17 | 64.40 | 51.4% | 100% | 6.61° | No |
| 3 | Marius Hills | 62.32 | 49.4% | 100% | 5.53° | No |
| 4 | Shackleton | 60.21 | 49.6% | 92.8% | 34.52° | Yes |
| 5 | Vallis Schröteri | 56.91 | 53.1% | 100% | 11.16° | No |
| 6 | Von Kármán | 47.62 | 49.4% | 0% | 0.76° | Yes |

Nobile wins four of five mission profiles. Apollo 17 wins the low-risk crewed sortie (80.6 vs 80.1) and is the risk-averse alternative.

## Repository layout

```
config/          criteria, weights, sites, curated Tier C scores, provenance
scripts/         fetch, geometry, table-building, scoring, dashboard generation
data/raw/        cached NASA responses
data/interim/    intermediate ephemeris and elevation data
data/processed/  rankings, scores, sensitivity, gaps, GeoJSON, recommendation
placeholders/    header-only schemas for missing LROC/LOLA/thermal/ISRU/relay data
web/             static dashboard (HTML/CSS/JS + local imagery)
tests/           offline regression tests
```

## Data attribution

NASA/JPL Horizons; NASA Moon Trek (LRO LOLA/LROC, PSR catalogue); NASA Image and Video Library. NASA does not endorse this analysis. The "lightning" requirement is interpreted as **solar lighting/illumination**, because the Moon has no appreciable atmosphere and therefore no weather lightning.
