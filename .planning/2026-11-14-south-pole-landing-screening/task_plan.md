# Task Plan: South-Pole Landing Screening

## Goal
Deliver a validated, NASA-data-driven lunar south-polar landing-site screening and comparison tool for 80–90°S, with an interactive map, date-aware illumination/comms analysis, clustered candidate regions, and a non-certified pinpoint candidate.

## Next Step
Recover and finish the in-progress Lunaria frontend, validate its generated data contract and browser behavior, then run the final cached rebuild and guideline review.

## Current Phase
Phase 3

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Document in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Preserve and park existing whole-Moon work
- [x] Inspect available 80–90°S DEM, Barker 5 m tiles, Artemis III candidate layer, and NASA ephemeris data
- [x] Define independent scoring criteria and acceptance gates
- **Status:** complete

### Phase 3: Implementation
- [x] Build south-polar DEM acquisition, coarse horizon masks, and 1 km screening grid
- [x] Make the scoring config authoritative; fix dark-period, thermal, PSR-edge, and ephemeris contracts
- [x] Add ~148 m shortlisted-region refinement and a provisional pinpoint seed
- [x] Implement normalized dual scoring, stable candidate regions, sliders, date status, and Dirichlet sensitivity
- [x] Archive the six-site presentation and make the polar dashboard/report/handoff the default
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Run focused unit and pipeline tests
- [x] Verify Barker 2024–2026 illumination-ranking status without fabricating missing data
- [x] Verify constraints, score agreement, sensitivity outputs, and Sun/Earth geometry
- [ ] Run final full suite, dashboard smoke test, secret scan, and two-axis review
- [ ] Validate the redesigned NASA/Lunaria dashboard at desktop and mobile sizes against the current Web Interface Guidelines
- **Status:** in_progress

### Phase 5: Delivery
- [ ] Review generated polar outputs and ensure no whole-Moon work was reused
- [ ] Deliver winner, validation result, caveats, and remaining data needs
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Scope is lunar south pole only, 80–90°S. | User explicitly superseded the whole-Moon scope; global work must not be built on. |
| Preserve existing uncommitted whole-Moon work in a named git stash. | User explicitly prohibited deleting it or building on it; the stash preserves tracked, untracked, and generated binary files without committing them. |
| Polar map output is ~1 km cells, aggregated from the ~151 m source DEM. | User specified this output scale and source. |
| Use a two-stage horizon model: optimistic 1 km full-cap screening, then ~148 m source-raster recomputation for every shortlisted cell. | User selected this practical replacement for a prohibitively large fine-resolution full-cap time cube; the second stage restores local ridge detail before the final ranking. |
| Use Barker 5 m LOLA LDEMs for pinpoint slope/hazard screening. | 5 m slope is meaningful at the pad scale; 1 km slope is only a roughness proxy. |
| Keep six legacy points only as validation benchmarks. | Avoid anchoring the new candidate score map to the old six-site set. |
| Use weighted sum and weighted geometric mean; headline geometric score. | User rejected a 50/50 consensus and requested rank agreement instead. |
| Use 1,000 Dirichlet weight draws and report each candidate region's top-rank share. | User specified this sensitivity method in the prior correction. |
| Show eight normalized indicators but weight only independent suitability dimensions; fold safety into terrain and keep data maturity as confidence only. | User explicitly selected this interpretation after double-counting concerns. |
| No hard Earth-visibility disqualification; report relay availability as unknown. | User explicitly selected this screening assumption. |
| Apply slope p90 >15° and sunlight <4% only as configurable, labeled assumptions, with solar evaluated after the other hard filters. | User specified both cutoffs and asked that they be identified as assumptions. |
| Never fabricate Artemis III candidate-region polygons or unverified Barker tile provenance. | NASA Moon Trek catalog lacks the 13-feature layer; the Barker article documents only Sites 1, 4, 7, and 11. |
| Use the installed rasterio/numpy stack for raster processing and declare it as a project dependency if needed. | Full 1 km polar raster horizon/illumination aggregation is not practical or reliable with the existing standard-library-only site sampler. |
| Make the polar product the default and preserve the six-site product as an archive. | User selected the polar-first presentation while retaining prior work. |
| Use a two-stage terrain model. | Full-cap screening stays fast at 1 km; shortlisted regions are recomputed on the ~148 m DEM before summary. |
| Report an exact provisional seed, not a certified pad, until 5 m Barker/LROC data arrives. | The available raster cannot resolve landing hazards. |
| Weight sliders rerank fixed baseline regions without reclustering. | Stable region identities make slider results interpretable and reproducible. |
| Date controls show six-hour candidate status while suitability maps remain 2024–2026 aggregates. | This supplies date awareness without shipping the full raster time cube. |
| Track compact products and compressed metrics, not reproducible 35/54 MB CSV working files. | Keeps the repository reviewable while retaining reusable measured data. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial whole-Moon exploration agent could not be read on first attempt. | Read its completed result after its completion notification; no implementation work was delegated. |
| First plan update patch used stale section text after the stash phase had already changed. | Re-read the selected plan and applied an updated patch against its current contents. |
| NASA/ArcGIS searches did not locate the authoritative 13-region geometry layer or all requested Barker tiles. | Preserve source gap explicitly; only ingest verified sources and identify the missing inputs in the UI/report. |
