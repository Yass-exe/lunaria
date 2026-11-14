# Lunaria: Six-Site Lunar Landing Analysis

**A NASA-data screening of terrain, solar power, Earth visibility, science, ISRU access and operational risk.**

Analysis date: **2026-11-14**  
Ephemeris window: **2026-11-14 → 2027-11-14**, 1-hour steps  
Primary question: *Which of six candidate sites offers the best pinpoint landing location for a first sustained lunar presence?*

> This is a screening and decision-support product. It is **not** a flight-certified landing site, a hazard map, or a link-budget authority.

---

## 1. Executive summary

**Recommendation: Nobile Crater Rim / Connecting Ridge (84.2°S, 60.7°E).**

Nobile Ridge scores **81.1/100** under the balanced mission profile and wins **four of five** mission profiles. Under 5,000 joint weight-and-score perturbation draws it is rank 1 in **99.96%** of cases. The recommended pinpoint candidate is:

| Pinpoint candidate | Value |
|---|---|
| Latitude | **84.2005°S** |
| Longitude | **60.7373°E** |
| Offset from supplied coordinate | **115 m** |
| Pad slope p90 | **5.5°** |
| Open sky above 5° | **88.3%** |
| Pad elevation | **1,118 m** |
| Source DEM | LOLA south-pole 75°S+ mosaic, 30 m/px |

The win is driven by a combination no other site matches: **71.8% annual solar availability**, a **5.8° site slope p90**, and a mapped PSR edge only **3.1 km** away. It is not a clean sweep: direct-to-Earth visibility is only **63.0%** of the year, with a **269-hour** longest outage, so a relay is mandatory.

**Runner-up: Apollo 17 — Taurus-Littrow Valley (64.4/100).** Apollo 17 wins the **low-risk crewed sortie** profile at **80.6**, essentially tied with Nobile at 80.1. It has **100%** Earth visibility, no relay, the best ground truth (Tier A), and a well-characterised valley floor. It gives up polar ISRU, has a 14-day night, and cannot match Nobile's power/ISRU combination.

**The most important negative result:** the supplied **Shackleton Crater Rim** coordinate (89.9°S, 0°E) is *not* the best polar site in this set. It is steep (slope p90 **34.5°**), has only **49.6%** solar availability and **92.8%** Earth visibility. The famous "Peak of Eternal Light" is not located at exactly this coordinate; a real Shackleton mission would need to target a specific illuminated ridge, not the crater rim point as supplied.

---

## 2. Ranking

Baseline profile weights: solar 20%, Earth link 18%, terrain 16%, science 14%, ISRU 12%, thermal 8%, safety 7%, data maturity 5%.

| Rank | Site | Score /100 | Solar | Earth >5° | Longest Earth outage | Slope p90 | PSR edge (approx.) | Relay? | Pinpoint p90 | Pad offset |
|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | **Nobile Crater Rim / Connecting Ridge** | **81.07** | 71.8% | 63.0% | 269 h | 5.78° | 3.10 km | Yes | 5.49° | 115 m |
| 2 | Apollo 17 — Taurus-Littrow Valley | 64.40 | 51.4% | 100.0% | 0 h | 6.61° | n/a | No | 8.93° | 91 m |
| 3 | Marius Hills | 62.32 | 49.4% | 100.0% | 0 h | 5.53° | n/a | No | 5.20° | 74 m |
| 4 | Shackleton Crater Rim | 60.21 | 49.6% | 92.8% | 113 h | 34.52° | 4.24 km | Yes | 33.91° | 235 m |
| 5 | Vallis Schröteri & Cobra Head | 56.91 | 53.1% | 100.0% | 0 h | 11.16° | n/a | No | 16.54° | 128 m |
| 6 | Von Kármán Crater | 47.62 | 49.4% | 0.0% | 8,761 h | 0.76° | n/a | Yes | 0.76° | 28 m |

*PSR edge is the approximate distance from a PSR centroid-and-area catalogue, not a PSR polygon. Non-polar sites have no meaningful polar PSR access and use a documented analyst score for ISRU instead.*

### Criteria matrix (baseline sub-scores)

| Site | Solar | Earth | Terrain | ISRU | Science | Thermal | Safety | Data |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Nobile Ridge** | 70.7 | 78.8 | **95.7** | **93.9** | 90 | 60 | 65 | 85 |
| Apollo 17 | 25.4 | **100** | 95.1 | 5 | 80 | 45 | **85** | **100** |
| Marius Hills | 20.8 | **100** | 97.2 | 18 | 85 | 40 | 55 | 70 |
| Shackleton | 21.3 | **100** | 11.6 | 87.6 | **95** | 55 | 45 | 95 |
| Vallis Schröteri | 29.2 | **100** | 83.3 | 5 | 88 | 35 | 25 | 65 |
| Von Kármán | 21.0 | 0 | **99.9** | 10 | **96** | 40 | 80 | 80 |

### Mission-profile winners

| Profile | Winner | Score | Runner-up | Score | Margin |
|---|---|---:|---|---:|---:|
| Balanced polar base | **Nobile Ridge** | 81.1 | Apollo 17 | 64.4 | 16.7 |
| Polar ISRU priority | **Nobile Ridge** | 81.8 | Shackleton | 60.2 | 21.6 |
| Low-risk crewed sortie | **Apollo 17** | 80.6 | Nobile Ridge | 80.1 | 0.4 |
| Science / geology priority | **Nobile Ridge** | 83.3 | Apollo 17 | 76.9 | 6.4 |
| Communications first | **Nobile Ridge** | 79.9 | Apollo 17 | 76.8 | 3.1 |

The low-risk sortie result is effectively a tie. The decision between Apollo 17 and Nobile Ridge for a *short* mission is a risk-posture choice; for a *sustained polar presence*, Nobile is the clear leader.

---

## 3. Why Nobile Ridge wins

### Measured evidence

- **Power:** the Sun is above the modelled local terrain horizon **71.8%** of the year, the highest in the set. The longest continuous dark period is **125 h** (about 5.2 days), versus roughly 356 h (14.8 days) at the equatorial sites.
- **Terrain:** site slope p90 is **5.78°**, roughness **3.08 m**, and the DEM-screened pad improves p90 to **5.49°**. This is the flattest credible polar terrain in the set.
- **ISRU proximity:** the nearest mapped PSR edge is approximately **3.1 km** away (Nobile/Amundsen PSR). This is a *proximity proxy*, not an ice detection.
- **Earth geometry:** direct-to-Earth visibility above 5° terrain clearance is **63.0%** of the year. The longest outage is **269 h**. A relay is required for continuous communications; the site is still far better connected than the far side.

### Tier C judgments

Science **90**, thermal **60**, crew safety **65**, data maturity **85**. These are analyst rubrics, not measurements. The thermal score is particularly weak evidence because no Diviner time series was ingested.

### What would change the answer

- A **1–2 m/px LROC NAC DTM and 0.5–1 m/px orthophoto** could reveal boulders or small scarps that the 30 m LOLA DEM cannot resolve. This is the top P0 data request.
- A **relay link budget** could turn the 269-hour direct-to-Earth outage from a manageable constraint into a mission driver.
- **Diviner temperatures** could lower or raise the thermal score substantially; the current 60/100 is a qualitative polar-temperature judgment.

---

## 4. Site-by-site assessment

### 4.1 Nobile Crater Rim / Connecting Ridge — rank 1, 81.07

**Measured:** solar 71.8%, Earth >5° 63.0%, longest Earth outage 269 h, site slope p90 5.78°, roughness 3.08 m, PSR edge ~3.10 km.  
**Pinpoint:** 84.2005°S, 60.7373°E; 115 m from the supplied point; pad p90 5.49°; open sky >5° 88.3%.  
**Strengths:** best combined power, terrain and ISRU access; four of five profile wins.  
**Risks:** relay required; 30 m/px DEM is not landing-hazard resolution; thermal and safety scores are Tier C.  
**Decision:** best balanced polar base and the recommended site.

### 4.2 Apollo 17 — Taurus-Littrow Valley — rank 2, 64.40

**Measured:** solar 51.4%, Earth >5° 100%, no outage, site slope p90 6.61°, roughness 1.64 m.  
**Pinpoint:** 20.1975°N, 30.7981°E; 91 m offset; pad p90 8.93°; open sky >5° 100%.  
**Strengths:** continuous direct-to-Earth, Tier A ground truth, benign valley floor, best low-risk crewed sortie.  
**Risks:** no polar ISRU; 14-day night; the pinpoint pad is rougher than the site coordinate because the pad objective favours horizon openness.  
**Decision:** best short-duration or risk-averse crewed mission; not the best sustained polar base.

### 4.3 Marius Hills — rank 3, 62.32

**Measured:** solar 49.4%, Earth >5° 100%, slope p90 5.53°, roughness 1.66 m.  
**Pinpoint:** 14.0023°N, 55.9991°W; 74 m offset; pad p90 5.20°.  
**Strengths:** excellent trafficability and communications; premier volcanic/lava-tube science; 2 m/px NAC DTM at the site.  
**Risks:** no ISRU; 14-day night; skylights, rilles and boulder fields are unresolved at the site-scale DEM.  
**Decision:** strong science sortie, not a polar base.

### 4.4 Shackleton Crater Rim — rank 4, 60.21

**Measured:** solar 49.6%, Earth >5° 92.8%, longest outage 113 h, site slope p90 **34.52°**, roughness 5.74 m, PSR edge ~4.24 km.  
**Pinpoint:** 89.9033°S, 4.0946°W; 235 m offset; pad p90 33.91°; open sky >5° 57.2%.  
**Strengths:** exceptional PSR access and science value; dense 5 m LOLA coverage; 92.8% Earth visibility.  
**Risks:** the supplied rim coordinate is steep and only ~50% illuminated; the "Peak of Eternal Light" is not at this exact point. A real mission must target a specific ridge.  
**Decision:** high-value but coordinate-sensitive; do not treat the supplied point as a certified pad.

### 4.5 Vallis Schröteri & Cobra Head — rank 5, 56.91

**Measured:** solar 53.1%, Earth >5° 100%, slope p90 11.16°, roughness 3.06 m.  
**Pinpoint:** 23.5014°N, 48.1957°W; 128 m offset; pad p90 16.54°.  
**Strengths:** spectacular volcanic and spectral science; the Moon's largest sinuous rille; 100% direct-to-Earth.  
**Risks:** extreme relief, rille-edge hazards, no dedicated high-resolution NAC DTM at the exact site (global 118 m/px used); safety score 25/100.  
**Decision:** compelling robotic or highly constrained science target; not a first crewed base.

### 4.6 Von Kármán Crater — rank 6, 47.62

**Measured:** solar 49.4%, Earth >5° **0.0%**, terrain slope p90 **0.76°**, roughness 0.17 m, no polar PSR access.  
**Pinpoint:** 45.5007°S, 177.5990°E; 28 m offset; pad p90 0.76°; open sky >5° 100% (terrain only — Earth is below the horizon).  
**Strengths:** flattest terrain in the set, highest science value (96/100), SPA basin and Chang'e-4 ground truth.  
**Risks:** far-side site; direct-to-Earth is impossible, so a relay architecture is mandatory; 14-day night; 118 m/px global DEM is the weakest terrain evidence in the set.  
**Decision:** outstanding far-side science target, but not a viable direct-to-Earth base.

---

## 5. Method

### 5.1 Data sources

| Source | Use |
|---|---|
| **NASA/JPL Horizons** | Topocentric Sun and Earth apparent azimuth/elevation for each site on body 301 (Moon), 1-hour steps, 2026-11-14 → 2027-11-14. 105,132 samples across six sites. |
| **NASA Moon Trek / LRO LOLA & LROC** | Six site DEM assignments from five products: LOLA south-pole 5 m/px and 30 m/px, LOLA global 256 ppd, LROC NAC 2 m/px (Marius), LROC NAC DTM 5 m/px (Apollo 17). Slope, roughness, 5 km horizon profiles, hillshades. |
| **NASA Moon Trek PSR catalogue** | Approximate PSR proximity from a centroid-and-area catalogue. |
| **NASA Image and Video Library** | Site-context imagery and metadata (presentation only; no scoring input). 43 relevant records after filtering out Earth-observation and unrelated matches. |
| **NASA API portal** | Keyed APOD endpoint. APOD was intermittently returning HTTP 500; a lunar-themed record was retrieved on retry and cached, but it is illustrative only and has no effect on scoring. |

The NASA API key is stored only in the gitignored `.env` file (mode 600). It is never written to data products or logs; HTTP error messages are redacted.

### 5.2 Two geometry modes

- **Site mode:** the exact user-supplied coordinate. This is the primary ranking.
- **Pinpoint mode:** a pad within 1 km selected on a DEM search grid by 50% open-sky fraction, 35% local flatness, and 15% proximity. The pad is re-checked on a 500 m / 16 m grid. It is a **candidate pad**, not a certified landing site.

### 5.3 Terrain and horizon model

- Local terrain statistics from a 32×32 DEM sample over a 500 m box.
- Horizon profile from a 5 km radius, 2 m eye height, 1° azimuth bins, with circular smoothing.
- Slope p90 is the 90th percentile of central-difference slope on the DEM grid; roughness is the residual standard deviation from a fitted plane.
- The model does **not** resolve boulders, metre-scale scarps, or terrain beyond 5 km. It does **not** model the full 18.6-year lunar libration cycle; the one-year window is a planning proxy.

### 5.4 Scoring

Each criterion is normalized to 0–100 with a documented scale and combined as:

**S = Σ wᵢ · sᵢ**, with weights summing to 1. The baseline weights are listed in §2; the five profiles are in `config/profiles.json`.

**Sensitivity:** 5,000 Monte Carlo draws perturb weights by ±50% (renormalized), Tier A/B sub-scores by ±3 points (1σ), and Tier C sub-scores by ±10 points (1σ), clipped to [0, 100]. The headline top-1 probability is from this joint model; the weight-only probability is reported separately in `data/processed/sensitivity.csv`.

### 5.5 Evidence tiers

| Tier | Meaning | Examples |
|---|---|---|
| **A** | Ground truth | Apollo 17 surface data and traverse validation |
| **B** | Measured or documented | DEM terrain, Horizons ephemerides, PSR catalogue |
| **C** | Analyst judgment | Science value, thermal, safety, data maturity |

Tier C scores are the weakest link. The sensitivity report samples them at ±10 points; the ranking is robust to those perturbations, but that does not make the judgments measurements.

---

## 6. “Lightning” vs. lighting

The brief used the word **lightning**. The Moon has no appreciable atmosphere, so there is no weather lightning. This analysis interprets the requirement as **solar lighting / illumination**: the fraction of the year the Sun is above the local terrain horizon, plus the longest dark period and the effect of terrain shadowing.

Electrostatic dust lofting and solar energetic particle events are real lunar hazards, but they are **not** modelled here. They belong in a separate charging/radiation environment assessment.

---

## 7. Data gaps and the LROC/LOLA request

The pipeline records **34 gaps**: 8 P0, 18 P1, 5 P2, 3 P3. Every gap has a placeholder schema in `placeholders/` and an AOI + acceptance test in `data/processed/data_gaps.csv`.

### P0 requests

| Site | Dataset | AOI (approx. 4×4 km) | Request |
|---|---|---|---|
| **Nobile Ridge** | LROC NAC stereo DTM | 84.134–84.266°S, 60.047–61.353°E | NAC stereo pair + controlled DTM, 1–2 m/px, plus error map |
| **Nobile Ridge** | LROC NAC orthophoto | same | Radiometrically calibrated orthomosaic, 0.5–1 m/px |
| **Von Kármán** | LROC NAC stereo DTM | 45.434–45.566°S, 177.506–177.694°E | NAC stereo pair + controlled DTM, 1–2 m/px |
| **Von Kármán** | LOLA 5–20 m DEM | same | 5 m/px clip + shot-count/error layer |
| **Von Kármán** | LROC NAC orthophoto | same | 0.5–1 m/px calibrated orthomosaic |
| **Vallis Schröteri** | LROC NAC stereo DTM | 23.434–23.566°N, 48.128–48.272°W | NAC stereo pair + controlled DTM, 1–2 m/px |
| **Vallis Schröteri** | LOLA 5–20 m DEM | same | 5 m/px clip + shot-count/error layer |
| **Vallis Schröteri** | LROC NAC orthophoto | same | 0.5–1 m/px calibrated orthomosaic |

### Additional high-value requests

- **Nobile Ridge:** LOLA 5–20 m independent DEM check (P1); Diviner thermal time series (P1); LEND water-equivalent hydrogen (P1); Mini-RF CPR (P2); relay link budget (P1).
- **All sites:** Diviner thermal maps/time series (P1); LROC NAC orthophoto and DTM for pad certification (P1 where not already P0); relay link budget (P1/P2).
- **Shackleton:** LROC NAC DTM/ortho at 1–2 m/px to test whether a specific illuminated ridge near the rim is a viable pad (P1). The supplied coordinate itself is too steep for a first base.

**Acceptance targets:** vertical error < 1 m (1σ); slope error < 2° at 5 m baseline; orthorectification to the DTM with geolocation < 5 m; full AOI coverage with no interpolated holes larger than 2 pixels.

---

## 8. Limitations

1. The illumination and Earth-link fractions use a **5 km terrain horizon** and a **one-year** Horizons window. Terrain beyond 5 km and the 18.6-year libration cycle are not fully modelled.
2. Terrain scores come from **5–118 m/px** DEMs sampled on a 32×32 grid. They are screening products, not landing-hazard certification. Boulder-scale hazards are unresolved.
3. Science, thermal, safety and data-maturity scores are **Tier C analyst judgments**, not measurements.
4. PSR edge distance is approximated from a **centroid-and-area catalogue**, not PSR polygons. It is not an ice detection.
5. Direct-to-Earth fraction below 99% triggers a **relay-required** flag. No relay link budget was ingested; the flag is a screening threshold, not a communications architecture.
6. APOD was intermittently unavailable (NASA-side HTTP 500) during the build; a record was cached on retry. It is illustrative only, and image-library metadata and Moon Trek products were unaffected.
7. The pinpoint pad is selected by a DEM objective, not by a lander-specific hazard model. It must be re-evaluated with NAC DTM/ortho and a landing-dispersion analysis.

---

## 9. Reproducibility

```bash
cd /home/yass/lunaria

# Optional: refresh cached NASA data (network)
python3 scripts/fetch_terrain.py
python3 scripts/fetch_horizons.py
python3 scripts/fetch_nasa.py

# Rebuild processed tables, scores and dashboard
python3 scripts/build_tables.py
python3 scripts/score_sites.py
python3 scripts/build_dashboard.py

# Offline regression tests
python3 -m unittest discover -s tests -v

# View the dashboard
python3 -m http.server 8765 --directory web
# open http://127.0.0.1:8765/
```

The dashboard also opens directly from `web/index.html` because `data.js`, `app.js` and the image assets are local.

### Key outputs

| File | Contents |
|---|---|
| `data/processed/site_ranking.csv` | Ranked scores for site and pinpoint modes |
| `data/processed/site_scores.csv` | Wide score table with ranks and top-1 probabilities |
| `data/processed/criteria_scores.csv` | Long-form raw values, sub-scores, tiers and rationales |
| `data/processed/sensitivity.csv` | 5,000-draw joint and weight-only robustness |
| `data/processed/site_ranking_by_profile.csv` | Rankings under all five mission profiles |
| `data/processed/recommendation.json` | Machine-readable verdict, rationale, caveats and P0 requests |
| `data/processed/sites.geojson`, `pinpoints.geojson` | Map-ready site and pad points |
| `data/processed/data_gaps.csv` | 34 gaps with AOIs, request specs and acceptance tests |
| `placeholders/*.csv` | Header-only schemas for missing datasets |

---

## 10. Bottom line

**Nobile Crater Rim / Connecting Ridge is the best balanced pinpoint landing bet in this six-site set.** It combines the highest solar availability, the flattest credible polar terrain, and the closest mapped PSR access. Its weaknesses are real — a mandatory relay and a 30 m/px DEM that is too coarse for final hazard certification — but neither is unique to Nobile, and both are addressable with the P0 LROC/LOLA requests above.

**Apollo 17 is the risk-averse alternative** and wins the low-risk crewed sortie by a hair. If the mission is short, near-side, and communications-critical, choose Apollo 17. If the goal is a sustained polar presence with ISRU access, choose Nobile Ridge — and certify the pad with the requested NAC DTM/ortho before committing.
