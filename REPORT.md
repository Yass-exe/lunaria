# Lunaria: Lunar South-Pole Landing-Region Screen

**Scope:** 80–90°S<br>
**Geometry window:** 2024-01-01 through 2026-01-01, six-hour samples<br>
**Analysis date:** 2026-11-14

> Decision support only. This is not a flight-certified landing site, landing ellipse, hazard map, communications link budget, or detection of lunar ice.

## 1. Executive result

The two-stage screen ranks **`polar-region-r167-c278`** first with a weighted geometric score of **0.6015 (60.15/100)**. Its best ~148 m source pixel is:

| Provisional seed property | Value |
|---|---:|
| Latitude | **85.4342°S** |
| Longitude | **10.5273°W** |
| Elevation | **1,402 m** |
| Source resolution | **148.44 m/px, server-resampled** |
| Seed weighted geometric score | **66.83/100** |
| Solar illumination | **48.51%** |
| Longest sampled dark run | **15.75 days** |
| 6.5-day continuous-light windows | **26.32%** |
| Earth above terrain | **95.08%** |
| Local slope p90 at available scale | **7.94°** |
| Approximate PSR edge | **2.60 km** |

This coordinate is a **provisional investigation seed**, not a pinpoint landing pad. A 148 m export cannot resolve metre-scale slopes, boulders, scarps, small craters, or landing-ellipse dispersion.

The region wins on balance: strong direct-to-Earth visibility, moderate terrain, and useful PSR proximity compensate for ordinary illumination. It is not robust enough to call a mission decision. Under 1,000 pure Dirichlet weight draws it ranks first **39.0%** of the time; the runner-up ranks first **38.5%**.

## 2. Refined ranking

| Rank | Stable region ID | Seed coordinate | WGM /100 | Sum /100 | Top-1 | Stage-1 rank |
|---:|---|---|---:|---:|---:|---:|
| 1 | `polar-region-r167-c278` | 85.4342°S, 10.5273°W | **60.15** | 62.75 | **39.0%** | 5 |
| 2 | `polar-region-r266-c417` | 86.0628°S, 73.5020°E | 59.10 | 61.01 | 38.5% | 1 |
| 3 | `polar-region-r165-c419` | 84.1304°S, 40.5055°E | 58.16 | 59.39 | 3.1% | 4 |
| 4 | `polar-region-r178-c423` | 84.2718°S, 43.9967°E | 58.03 | 59.60 | 7.3% | 2 |
| 5 | `polar-region-r167-c266` | 85.3331°S, 14.9759°W | 57.46 | 59.19 | 0.0% | 3 |
| 6 | `polar-region-r281-c404` | 86.5777°S, 77.4045°E | 51.41 | 57.31 | 12.1% | 6 |

Weighted sum and weighted geometric mean select the same winner and have strong rank agreement after refinement (Spearman **ρ = 0.9429**). That agreement does not remove input uncertainty.

The ranked clusters are not assigned Artemis names. NASA's public announcement supplies 13 names, but no authoritative polygon layer was found in the inspected Moon Trek catalogue. Inventing boundaries or assigning names by visual proximity would create false provenance.

## 3. Winner evidence

### Measured or derived

- **Solar:** 48.51% of six-hour samples clear the ~148 m terrain horizon. The longest sampled dark run is 15.75 days.
- **Earth visibility:** 95.08% clears the terrain horizon after correcting the Moon-centred direction for lunar-surface parallax. Relay availability remains unknown and Earth visibility is therefore graded, not a hard filter.
- **Terrain:** local source-scale slope p90 is 7.94°. This is useful for regional screening only; it is not a 5 m pad slope.
- **PSR access:** 2.60 km to the nearest equivalent-area PSR edge. The source provides centroids and areas rather than polygons, so this is an explicit circle approximation—not an ice detection.
- **Elevation:** 1,402 m in the Moon Trek LOLA south-polar export.

### Proxies

- **Science placeholder:** fixed at 0.5 for every candidate until an independent geology/spectral layer is ingested. This neutral value prevents terrain slope from being weighted twice.
- **Thermal proxy:** linear poleward stability, 0 at 80°S and 1 at 90°S. It is not temperature data and must be replaced by Diviner.
- **Raster-valid coverage:** 100% in the server-resampled export. This is not native LOLA shot coverage or proof that every raster pixel is an observation.

## 4. Method

### Inputs

- **NASA Moon Trek / LRO LOLA:** `LRO_LOLA_DEM_SPole75_30mp_v04`, exported as a 4096×4096 Moon2000 south-polar GeoTIFF over ±304 km. The server export is 148.44 m/px; its service advertises a 30 m native product.
- **NASA/JPL Horizons:** body-fixed sub-solar and sub-Earth longitude/latitude plus Moon-centre range. There are 2,925 aligned timestamps per body.
- **Moon Trek PSR catalogue:** 164 centroid-and-area records.

### Stage 1: full-cap screen

The source DEM is summarized to 608×608 one-kilometre cells. For each valid 80–90°S cell, the highest source pixel acts as an optimistic ridge observer and maximum source elevation preserves obstruction crests. Ninety-six azimuth bins extend to 60 km and include lunar curvature. The operational cluster gate is WGM ≥ 0.60, eight-way connectivity, and at least three cells. It is a tunable candidate-forming rule, not a safety threshold.

### Stage 2: source-raster refinement

All source pixels inside the six stage-one clusters receive new ~148 m horizons and two-year Sun/Earth calculations. Region dimensions are the medians of eligible refined cells; the best fine cell is retained as the provisional seed. Exact 5 m Barker and 1–2 m LROC terrain are absent, so no fine landing-hazard filter is claimed.

### Scoring

Independent dimensions and balanced weights are:

| Dimension | Weight |
|---|---:|
| Solar power | 24% |
| Earth visibility | 20% |
| Terrain safety | 20% |
| ISRU/PSR access proxy | 16% |
| Neutral science placeholder | 10% |
| Thermal proxy | 10% |

Solar power geometric-means illumination utility and longest-dark-period utility. The dark utility reaches zero at 30 days—approximately one synodic lunar night. The 6.5-day continuity statistic is reported but not weighted, avoiding triple-counting the same shadowing behaviour. Crew safety aliases terrain and raster coverage remains confidence-only. Full formulas live in `config/polar_scoring.json` and are loaded as the sole scoring policy.

## 5. Validation

| Gate | Result |
|---|---|
| Moon2000 projection round trip | max error **0.0000 m — PASS** |
| Sun geometry vs topocentric Horizons | max ΔEl **0.00013°**, ΔAz **0.06906° — PASS** |
| Earth geometry vs topocentric Horizons | max ΔEl **0.00034°**, ΔAz **0.00304° — PASS** |
| Sum vs WGM cell ranking | Spearman **0.9058 — PASS** |
| Barker Site 01/04/07/11 ranking | **FAIL/BLOCKED** |

The Barker check explicitly fails its validation gate because the exact ROI geometry, 5 m LDEMs, error surfaces, valid-pixel masks, and solar-disk implementation are absent. The older supplied Nobile coordinate at 84.2°S is not Barker Site 01 and cannot substitute for it.

## 6. Limitations

1. Stage one is an optimistic ridge screen: every 1 km cell uses its highest source pixel as observer.
2. Stage two is still 148 m/px and cannot certify a landing pad.
3. Horizons is sampled every six hours; brief lighting or communications transitions can occur between samples.
4. The window spans two years, not the full 18.6-year lunar nodal/libration cycle.
5. The horizon uses 96 azimuth bins and terrain to 60 km.
6. PSR edge distance is an equivalent-circle approximation and says nothing about volatile concentration.
7. Science is a neutral placeholder and thermal is a Tier C proxy; neither is a measurement.
8. Direct-to-Earth visibility is not a link budget; relay availability is unknown.
9. The operational 0.60 cluster threshold and score weights encode priorities, not mission safety requirements.

The original brief's “lightning” is interpreted as **solar lighting/illumination**. The Moon has no appreciable atmosphere and no terrestrial weather lightning.

## 7. Exact LROC/LOLA request

For the provisional seed at **85.4342°S, 10.5273°W**, request the approximately 4×4 km AOI:

- latitude **85.500177°S to 85.368266°S**
- longitude **11.355805°W to 9.698699°W**

Priority data:

1. **Barker/LOLA 5 m LDEM:** exact product ID, controlled GeoTIFF, vertical-error layer, LOLA shot-count layer, and valid/interpolated-pixel mask.
2. **LROC NAC stereo DTM:** 1–2 m/px with source pair IDs, control report, and vertical-error map. Acceptance: vertical error <1 m (1σ), slope error <2° at 5 m baseline, geolocation <5 m.
3. **LROC NAC orthophoto:** 0.5–1 m/px, radiometrically calibrated and orthorectified to that DTM, with incidence/emission metadata.
4. **Official Artemis III polygons:** all 13 named regions, source CRS, version, release date, and provenance.

Preferred coordinate reference: the Moon2000 south-polar stereographic CRS recorded in the supplied GeoTIFF, with a WGS84-style lon/lat footprint included for discovery.

Secondary requests are Diviner temperatures, LEND WEH, Mini-RF CPR/S1, and a relay link budget. Every request and acceptance test is reusable in `data/processed/polar_data_gaps.csv`; destination CSVs under `placeholders/` remain header-only until real records arrive.

## 8. Reproduce

```bash
cd /home/yass/lunaria
python3 -m pip install -r requirements-polar.txt
python3 scripts/build_polar.py
python3 -B -m unittest discover -s tests -v
python3 -m http.server 8765 --directory web
```

The final reviewed full build completed in **2:04.33**, below the ten-minute budget. Integrity hashes are in `data/processed/polar_data_manifest.json`.
