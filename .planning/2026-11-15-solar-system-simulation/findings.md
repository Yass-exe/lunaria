# Findings & Decisions

## Requirements
- Render the Sun, Earth, and Moon in a Three.js scene with the Sun as the primary light source.
- Animate orbital motion, axial rotation, axial tilts, and Moon orbit around Earth.
- Provide an explicit Visually Scaled / True-to-Scale switch for relative sizes and distances.
- Provide OrbitControls for rotate, zoom, and pan; speed control from paused through 100x; focus buttons for Sun, Earth, and Moon.
- Supply one self-contained HTML file using CDN links.
- Implement a smooth dual-theme HUD and 3D environment transition.
- Use warm light-mode beige/cream, sage/terracotta accents, and gentle light atmospheric dust motes.
- Use forest/indigo/violet dark-mode palette, starfield/nebula treatment, and glowing sage active controls.
- Keep controls responsive, keyboard-accessible, and usable on narrow viewports.

## Research Findings
- The environment has no dedicated approved visual target; this is a create-from-brief experience.
- Three.js examples are best used through version-pinned ES modules with an import map for OrbitControls.
- The user-supplied palette is the authoritative visual system; malformed original codes are resolved exactly as normalized in the brief.
- True physical scale is intentionally extremely difficult to keep all bodies legible in one viewport; the interface must disclose that the scale mode changes both display sizes and distances.

## Design Contract
- **Thesis:** Treat the simulation as a calm observatory instrument: a centered orbital mechanism with an asymmetrical frosted telemetry rail and a small time dial. Avoid generic dashboard-card grids and avoid putting every control into the center.
- **Visual world:** Warm sunlit parchment with sage and muted terracotta in light mode; twilight pine and cosmic indigo with violet glass and sage signal color in dark mode. Typography pairs a clean sans serif with an italic serif used only for atmospheric scene captions.
- **Story:** A visitor immediately sees the three-body motion, understands the scale mode and simulation rate, and can move the camera focus between bodies.
- **First viewport:** Full-bleed orbiting system as the hero; compact left-side title and scale control; right-side glass telemetry rail; bottom-center focus and speed controls; small orbital progress dial at lower left on desktop.
- **Authority:** Create. The brief supplies the visual palette and all core product requirements.
- **Target:** No approved image target. Build directly from the brief.
- **Finish:** Verify default light and dark themes, paused and accelerated motion, True-to-Scale and Visually Scaled states, focus buttons, OrbitControls, desktop and mobile layouts, reduced-motion behavior, and no console/runtime errors.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Keep body hierarchy and derive positions from orbital phases | Allows time scale, focus tracking, and orbit lines to share one motion model |
| Use visual mode for legibility and true mode for relative physical ratios | Fulfills both the requested educational readability and the true-scale inspection switch |
| Use a radial SVG progress dial as the signature interaction | Gives simulation time a distinctive system-specific visual rather than an ordinary slider-only HUD |
| Use custom point sprites for atmospheric particles | Keeps the experience self-contained and lets particle treatment respond to theme |
| Use an accessible segmented theme switch with animated thumb | Makes light/dark state immediately legible without emoji or decorative iconography |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- User brief and explicitly supplied palette
- Three.js r168 CDN modules via jsDelivr
- `prefers-reduced-motion` media query for motion-sensitive users
