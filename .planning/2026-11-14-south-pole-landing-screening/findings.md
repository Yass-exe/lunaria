# Findings & Decisions

## Requirements
- Project scope is **lunar south pole only, 80–90°S**. Drop whole-Moon/global mapping from the new implementation.
- Existing uncommitted whole-Moon changes must be preserved and parked (not deleted); do not build on them.
- Study map: ~1 km full-cap screening cells derived from the ~151 m south-polar DEM, followed by source-raster horizon/illumination recomputation for every shortlisted cell. This two-stage model supersedes the original fine-resolution full-cap requirement by explicit user decision.
- Pinpoint stage: Barker 5 m LOLA LDEMs for Site01, Site04, Site11, Site23, and Site20v2. At 1 km scale, slope is only a terrain-roughness proxy; use meaningful slope p90 at 5 m for pinpoint screening.
- Candidate list: Artemis III 13 candidate-regions layer. Overlay it on the south-polar map and cluster adjacent high-scoring cells into distinct regions.
- Six legacy coordinates are validation benchmarks only, never scoring anchors. Validate against Barker et al. (2021) illumination ranking for 2024–2026, with Site 01 expected to rank best; report `pass: false` / blocked when exact Barker inputs are absent.
- Eight scoring criteria use documented utilities normalized to 0–1. Mark proxies visibly, show data maturity/coverage, and never describe proxies as measurements. Merge or group correlated factors to avoid double counting.
- Configurable thresholds: slope p90 >15° and solar illumination <4%; both are assumptions unless a sourced threshold is established. Apply the solar cutoff after other hard filters. Do not hard-filter Earth visibility while relay availability is unknown; explicitly state the relay assumption.
- Balanced default weights and functional normalized UI sliders. Compute weighted sum and weighted geometric mean with identical weights; headline the geometric score and report rank agreement.
- Sensitivity: 1,000 Dirichlet weight perturbations, reporting each candidate region's percentage of draws ranked #1.
- Report a south-polar screening winner plus a pinpoint candidate within 1 km of its ranked seed. Neither is hazard-certified.

## Research Findings
- The committed README is still a six-site comparison; no separate challenge brief, Barker citation, or Site 01 mapping was found in the repository. The user's latest scope explicitly supersedes the older six-site/whole-Moon work.
- Relevant Barker publication metadata: Barker et al., “Improved LOLA elevation maps for south pole landing sites: Error estimates and their impact on illumination conditions,” DOI [10.1016/j.pss.2020.105119](https://doi.org/10.1016/j.pss.2020.105119). The exact Site 01 coordinates/data and quantitative validation tolerance still need verification from the paper or its supplemental material.
- OpenAlex identifies an accepted manuscript PDF for the Barker paper at `https://www.sciencedirect.com/science/article/am/pii/S0032063320303329`; DOI landing page itself redirects through a JavaScript access flow. The paper's manuscript/PDS data links can be checked directly during the validation-source investigation.
- NASA NTRS search confirms Barker et al. (2021) generated four high-priority, 16×16 km LOLA LDEMs at 5 m/pixel; the paper quantifies typical slope uncertainty at about 1.5–2.5° and discusses how DEM error propagates into horizon/illumination predictions. NTRS record 20205009660 is publicly distributable.
- The Barker paper identifies its four LDEMs as Sites 1, 4, 7, and 11 (not the user's full list of 01, 04, 11, 23, and 20v2). Site 1 is the Connecting Ridge between Shackleton and de Gerlache; Site 4 is the Shackleton rim; Site 7 is a far-side peak near Shackleton; Site 11 is the de Gerlache rim. The 2024-01-01 to 2026-01-01 interval is explicitly described as the earliest Artemis target window.
- Barker states the 5 m LOLA LDEM has valid data in only about 10% of pixels due to track gaps; any 5 m slope p90 must disclose valid-cell coverage and should not silently interpolate missing pixels.
- Barker's study computes illumination at 5 m/pixel over 16×16 km ROIs; it highlights contiguous areas with average solar-disk visibility >70% over Jan 1, 2024–Jan 1, 2026 and area >2,500 m². Its Site 1/4/7/11 naming is inherited from Mazarico et al. (2011); the requested Site 23 and Site 20v2 are not covered by this paper and require independent validation/data discovery.
- Prior worktree contains uncommitted whole-Moon changes to reports/dashboard/scoring plus generated global and south-pole products, scripts, tests, and raw grid tiles. These are to be stashed intact before any polar implementation.
- Whole-Moon WIP is now preserved as `stash@{0}` with message `Park whole-Moon WIP before polar-only implementation`; the working tree is clean except for this task's `.planning/` files. The stash includes ~194 MB of generated grid tiles; do not pop/apply it or use its generated score products.
- The committed repository already has raw NASA Moon Trek service metadata, 5 m Shackleton LOLA data, 30 m south-polar DEM data, PSR catalogue, and six-site Horizons files. The ~151 m full south-polar mosaic/grid artifacts were in the parked whole-Moon work and must be fetched/rebuilt independently for this polar task rather than reused from the stash.
- Initial searches did not locate Barker Site01/04/11/23/20v2 identifiers in the committed scripts/config. `services.json` includes `Site01_ROIs_SP`; exact service IDs, coverage and relation to Barker's 5 m LDEMs require source metadata inspection.
- The committed south-polar LOLA 30 m service metadata uses the Moon2000 south-polar stereographic projection, covers a square extent ±457.44 km, and reports native pixel size 30 m. The existing 151 m mosaic was a downsampled derivative, not a native 151 m source.
- The cached Moon Trek service catalog contains `Site01_ROIs_SP`, but searches did not locate the full 13-region Artemis III candidate layer or the named Barker 5 m site products. Treat the catalog as incomplete/stale until live service metadata is queried.
- Live NASA Moon Trek catalog confirms the south-polar 30 m and 5 m LOLA services. `Site01_ROIs_SP` contains only 7 features; `SSC_Impact_Site_v3_SP` contains 1 and `Intrepid_ScienceStations_AtoArtemis_SP` contains 5. None is the requested 13-region Artemis III layer.
- Moon Trek REST endpoints are publicly accessible without a NASA API key. Keep the existing key private and only pass it to NASA APIs that require it; do not attach it to public Moon Trek or JPL Horizons requests.
- NASA's official Artemis III release lists 13 regions: Faustini Rim A, Peak Near Shackleton, Connecting Ridge, Connecting Ridge Extension, de Gerlache Rim 1, de Gerlache Rim 2, de Gerlache-Kocher Massif, Haworth, Malapert Massif, Leibnitz Beta Plateau, Nobile Rim 1, Nobile Rim 2, and Amundsen Rim. NASA says these are within 6° of the pole and were screened for terrain slope, Earth communications, lighting, and launch-window timing.
- The official NASA release confirms that candidate selection is coupled to launch dates and says all 13 regions include access to sunlight during a planned 6.5-day surface mission. The current ArcGIS/Moon Trek catalog search did not return a 13-feature layer; the source geometries still need to be found rather than approximated without provenance.
- The committed `scripts/fetch_terrain.py` is a six-site sampler using 32×32 samples and 2.5 km regional horizons; `scripts/lunar_geom.py` computes one 360-bin horizon profile per point. The current implementation cannot directly provide full-region fine-DEM masks at 1 km output resolution.
- The committed `scripts/fetch_horizons.py` fetches one-hour Sun/Earth ephemerides only for the six configured sites over 2026–2027; it cannot yet support the 2024–2026 Barker comparison or all 13 candidate regions.
- The legacy eight criteria currently include solar illumination, Earth link, terrain, ISRU, science, thermal, crew safety, and data maturity. The solar criterion is only the fraction illuminated; crew safety text includes communications blackouts, overlapping Earth-link scoring. Terrain and safety are otherwise described as separate, but the safety criterion is curated qualitative judgment.
- Legacy terrain and thermal/science/safety/data utilities are unsuitable as-is for the polar grid: terrain scale mixes DEM resolutions, thermal is a curated score without Diviner inputs, and science/safety/data are analyst scores rather than spatially measured layers.
- The legacy scorer computes a compensatory weighted sum on 0–100 subscores, treats Tier C analyst scores as input, and runs ±50% uniform weight perturbations plus score noise. The new implementation must instead use 0–1 utilities, pure 1,000-draw Dirichlet weight sensitivity, and report region-level win rates.
- The legacy balanced profile weights solar .20, Earth link .18, terrain .16, science .14, ISRU .12, thermal .08, crew safety .07, and data maturity .05. These can inform a balanced starting profile only after the new criterion definitions are settled; do not copy the weights blindly if criteria are merged or redefined.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Separate physical suitability from data maturity/confidence where possible. | Data coverage is useful to judges but can bias candidate quality if treated as a measured site benefit. |
| Group correlated illumination/dark-period/continuity metrics into a single power criterion. | Avoid double-counting related time-series quantities. |
| Merge terrain safety with landing-hazard terrain metrics unless an independent safety measure is available. | Prevent slope/roughness from receiving multiple weights. |
| Retain Earth visibility as a graded criterion, not a hard fail. | Relay availability/inventory is unknown. |
| Do not restore or build on the 194 MB whole-Moon WIP stash. | User explicitly requested the WIP be parked and excluded from the new implementation. |
| Keep eight normalized indicators visible; use only independent dimensions in weighted suitability and display data maturity separately. | User confirmed this treatment to meet the eight-indicator requirement without double counting. |
| Raster processing may use numpy/rasterio already installed in the environment. | Full-resolution horizon ray casting and 1 km aggregation require raster-aware operations; preserve standard library for API access and scoring logic where practicable. |
| The 0.60 operational clustering cutoff remains unchanged. | With the 30-day dark scale, poleward thermal proxy, and corrected equivalent-area PSR edge proxy, the cached grid produces eligible contiguous regions at 0.60. |
| Treat `data_coverage_fraction` as raster-valid coverage, not native LOLA shot coverage. | The Moon Trek export is server-resampled and reports full raster coverage; it is not evidence that every pixel contains a native LOLA observation. |

## Current Implementation Findings
- `polar_model.py` already used a 30-day dark scale and excluded continuity, while `polar_scoring.json` still declared 6.5 days and weighted continuity. This duplicated policy is the root cause of stale calibration.
- `polar_illumination.py` currently rewards equatorward latitude for thermal stability; the agreed proxy must increase poleward and remain visibly Tier C.
- `psr_edge_km` currently contains nearest-centroid distance despite the PSR catalogue providing area. Equivalent-circle edge distance changes the calibrated 0.60 result from 17 cells/3 regions to approximately 62 cells/6 regions.
- The current full-cap horizon is computed after a 1 km maximum-elevation aggregation. The agreed replacement is an explicitly coarse first stage plus ~148 m recomputation for shortlisted regions.
- The generated 35 MB metrics and 54 MB score CSVs are rebuildable. Gzip sizes are approximately 11.5 MB and 19.4 MB; only compressed measured metrics need to be retained.
- `scipy` is imported but undeclared. The required maximum aggregation and PSR-distance work can be implemented with NumPy so the polar dependency set remains NumPy/Rasterio/Pillow.
- The resumed worktree already contains a substantial dashboard redesign: `web/index.html`, `web/styles.css`, and `web/app.js` account for most of the 6,565 changed lines, with a local NASA logo, favicon, and bundled fonts added under `web/assets/`.
- The selected plan is still in Phase 4 verification. The frontend should be recovered and reviewed in place rather than replaced or restarted.
- The recovered HTML already exposes the complete processing narrative rather than a decorative landing page: full-cap pipeline counts, all six refined regions, the 290,364-cell distributions, all 17,550 candidate status rows, live weighting, validation, data gaps, artifacts, policy, provenance, and caveats.
- The current visual concept is a restrained lunar field atlas. Its memorable element is the annotated polar plate; the surrounding UI uses editorial measurement panels rather than a generic card grid. The NASA mark is explicitly paired with an independent-analysis/non-endorsement statement.
- The 2026-11-15 Web Interface Guidelines review source requires, among other checks: visible keyboard focus, labels and semantic controls, reduced motion, transform/opacity-only motion, URL-reflected tab/filter state, `Intl` date/number formatting, explicit image dimensions, lazy below-fold images, touch treatment, safe-area handling, and non-breaking/typographic punctuation.
- The recovered JavaScript already persists layer, selected region, timeline index, weight priorities, and evidence tab in the URL; formats dates/numbers with `Intl`; adds live-region announcements; implements keyboard tab navigation; and exposes canvas descriptions for assistive technology.
- Timeline playback is user-triggered and pauseable. CSS and JavaScript both detect reduced motion, and all data-dense arrays are aggregated into canvas/distribution summaries rather than rendering hundreds of thousands of DOM nodes.
- Remaining guideline risks identified in the source review: no explicit `touch-action`, tap-highlight, safe-area, or fine-pointer overscroll treatment; range inputs lack `name`/`autocomplete`; and the hero’s CSS reveal needs inspection because the guideline permits only transform/opacity animation.

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Whole-Moon implementation has live worktree modifications and untracked generated files. | Preserved it in a named stash before changing the worktree; planning files were excluded. |

## Resources
- Prior handoff: `HANDOFF.md` (currently modified by the whole-Moon work; preserve it in the stash).
- Barker et al. 2021 DOI: https://doi.org/10.1016/j.pss.2020.105119
- NASA Moon Trek south-polar LOLA services and Barker tiles (URLs/coverage to be confirmed during discovery).
- NASA Artemis III candidate-regions layer (URL/format to be confirmed during discovery).
