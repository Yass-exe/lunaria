
(function () {
  "use strict";

  const D = window.LUNARIA_POLAR_DATA;
  const main = document.querySelector("main");
  if (!D) {
    if (main) {
      main.innerHTML =
        '<section class="section"><h1>Processed data missing</h1><p>Run <code translate="no">python3 scripts/build_polar_dashboard.py</code> to generate <code translate="no">web/data.js</code>.</p></section>';
    }
    return;
  }

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) =>
    Array.prototype.slice.call((root || document).querySelectorAll(selector));
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ----------------------------------------------------------------------
     Formatting (mirrors web/app.js conventions)
     ---------------------------------------------------------------------- */
  const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const decCache = new Map();
  function dec(digits) {
    if (!decCache.has(digits)) {
      decCache.set(
        digits,
        new Intl.NumberFormat("en-US", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        })
      );
    }
    return decCache.get(digits);
  }
  function int(value) {
    const number = Number(value);
    return Number.isFinite(number) ? intFmt.format(number) : "—";
  }
  function num(value, digits) {
    const number = Number(value);
    const places = digits == null ? 2 : digits;
    return Number.isFinite(number) ? dec(places).format(number) : "—";
  }
  function pct(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return num(number * 100, digits == null ? 1 : digits) + "%";
  }
  function coordLat(lat) {
    const number = Number(lat);
    if (!Number.isFinite(number)) return "—";
    return num(Math.abs(number), 4) + "°" + (number < 0 ? "S" : "N");
  }
  function coordLon(lon) {
    const number = Number(lon);
    if (!Number.isFinite(number)) return "—";
    return num(Math.abs(number), 4) + "°" + (number < 0 ? "W" : "E");
  }
  function coord(lat, lon) {
    return coordLat(lat) + ", " + coordLon(lon);
  }
  function bytes(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return "—";
    if (number >= 1e9) return num(number / 1e9, 2) + "\u00a0GB";
    if (number >= 1e6) return num(number / 1e6, 1) + "\u00a0MB";
    if (number >= 1e3) return num(number / 1e3, 1) + "\u00a0kB";
    return int(number) + "\u00a0B";
  }
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function stamp(value) {
    if (!value) return "—";
    try {
      return new Date(value).toUTCString();
    } catch (e) {
      return esc(value);
    }
  }

  function set(id, html) {
    const el = $(id);
    if (el) el.innerHTML = html;
  }

  function el(tag, html, cls) {
    const e = document.createElement(tag);
    e.innerHTML = html;
    if (cls) e.className = cls;
    return e;
  }

  /* ----------------------------------------------------------------------
     Generic data renderers — every key/value of the processed payload is
     shown, nested objects and arrays recurse into definition lists.
     ---------------------------------------------------------------------- */
  function formatScalar(key, value) {
    const k = String(key).toLowerCase();
    if (typeof value === "number") {
      if (k.includes("lat")) return coordLat(value);
      if (k.includes("lon")) return coordLon(value);
      if (k.includes("bytes")) return bytes(value);
      if (k.includes("fraction") || k.includes("score") || k.includes("proxy")) return pct(value);
      if (k.includes("km") || k.includes("m") || k.includes("deg")) return num(value);
      return int(value);
    }
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (value === null || value === undefined) return "—";
    if (k.includes("date") || k.includes("at") || k.includes("generated")) return stamp(value);
    return esc(value);
  }

  function renderObject(obj, opts) {
    opts = opts || {};
    const items = [];
    const depth = opts.depth || 0;
    const maxDepth = opts.maxDepth == null ? 4 : opts.maxDepth;
    for (const key of Object.keys(obj)) {
      const value = obj[key];
      const label = key
        .replace(/([A-Z])/g, " $1")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
      if (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        depth < maxDepth
      ) {
        items.push(
          `<dt class="dx-group">${esc(label)}</dt><dd><dl class="dx-dl">${renderObject(
            value,
            { depth: depth + 1, maxDepth }
          )}</dl></dd>`
        );
      } else if (Array.isArray(value)) {
        items.push(
          `<dt class="dx-group">${esc(label)}</dt><dd>${renderArray(
            value,
            { depth: depth + 1, maxDepth }
          )}</dd>`
        );
      } else {
        items.push(`<dt>${esc(label)}</dt><dd>${formatScalar(key, value)}</dd>`);
      }
    }
    return items.join("");
  }

  function renderArray(arr, opts) {
    if (!arr.length) return "<em>none</em>";
    if (
      typeof arr[0] === "object" &&
      arr[0] !== null &&
      !Array.isArray(arr[0])
    ) {
      return arr.map((v, i) => `<dl class="dx-dl dx-compact"><strong>Item ${i + 1}</strong>${renderObject(v, opts)}</dl>`).join("");
    }
    return `<ul class="dx-list">${arr
      .map(
        (v) =>
          `<li><span class="label">${esc(String(v).replace(/([A-Z])/g, " $1").replace(/_/g, " "))}</span><span class="value">${formatScalar(v, v)}</span></li>`
      )
      .join("")}</ul>`;
  }
  /* ----------------------------------------------------------------------
     Section renderers
     ---------------------------------------------------------------------- */
  function renderHeroMetrics() {
    const m = D.meta;
    const r = D.recommendation;
    return `
      <div class="dx-metric"><dt>Cells screened</dt><dd class="count" data-count-to="${m.cell_count}" data-count-fmt="int">0</dd></div>
      <div class="dx-metric"><dt>Refined cells</dt><dd class="count" data-count-to="${m.refined_cell_count}" data-count-fmt="int">0</dd></div>
      <div class="dx-metric"><dt>Winner score</dt><dd class="count" data-count-to="${r.winner_score}" data-count-fmt="pct">0%</dd></div>
      <div class="dx-metric"><dt>Regions</dt><dd class="count" data-count-to="${r.region_count}" data-count-fmt="int">0</dd></div>
      <div class="dx-metric"><dt>Region-time records</dt><dd class="count" data-count-to="${m.timeline_rows}" data-count-fmt="int">0</dd></div>
      <div class="dx-metric"><dt>Artifacts</dt><dd class="count" data-count-to="${m.artifact_count}" data-count-fmt="int">0</dd></div>
    `;
  }

  function renderMeta() {
    const m = D.meta;
    const rows = [
      ["Generated", stamp(m.generated_at)],
      ["Scope", esc(m.scope)],
      ["Window", stamp(m.window_start) + " \u2013 " + stamp(m.window_end)],
      ["Step", m.step_hours != null ? m.step_hours + " h" : "—"],
      ["Cells screened", int(m.cell_count)],
      ["Stage-1 cell size", m.stage1_cell_m != null ? m.stage1_cell_m + " m" : "—"],
      ["Stage-2 resolution", m.stage2_resolution_m != null ? num(m.stage2_resolution_m) + " m" : "—"],
      ["Refined cells", int(m.refined_cell_count)],
      ["Region-time records", int(m.timeline_rows)],
      ["Artifacts", int(m.artifact_count)],
      ["Artifact bytes", bytes(m.artifact_bytes)],
    ];
    return `<dl class="dx-dl">${rows
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
      .join("")}</dl>`;
  }

  function renderRecommendation() {
    const r = D.recommendation;
    const rows = [
      ["Status", esc(r.status)],
      ["Winner", esc(r.winner)],
      ["Winner score", pct(r.winner_score)],
      ["Regions", int(r.region_count)],
      ["Top-rank match", int(r.rank_agreement.top_rank_match)],
      ["Exact order match", int(r.rank_agreement.exact_order_match)],
      ["Spearman \u03c1", num(r.rank_agreement.spearman_rho, 3)],
    ];
    return `<dl class="dx-dl">${rows
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
      .join("")}</dl>`;
  }

  function renderSeed() {
    const s = D.recommendation.provisional_seed;
    const rows = [
      ["Candidate", esc(s.candidate_id)],
      ["Region", esc(s.region_id)],
      ["Latitude", coordLat(s.lat_deg)],
      ["Longitude", coordLon(s.lon_deg)],
      ["Elevation", s.elevation_m != null ? num(s.elevation_m) + " m" : "—"],
      ["Resolution", s.source_resolution_m != null ? num(s.source_resolution_m) + " m" : "—"],
      ["Solar illumination", pct(s.solar_illumination_fraction)],
      ["Longest dark days", s.longest_dark_days != null ? num(s.longest_dark_days) + " d" : "—"],
      ["Sunlight continuity", pct(s.sunlight_continuity_fraction)],
      ["Earth visibility", pct(s.earth_visibility_fraction)],
      ["Regional slope p90", s.regional_slope_p90_deg != null ? num(s.regional_slope_p90_deg) + "\u00b0" : "—"],
      ["Pinpoint slope p90", s.pinpoint_slope_p90_deg != null ? num(s.pinpoint_slope_p90_deg) + "\u00b0" : "—"],
      ["PSR edge", s.psr_edge_km != null ? num(s.psr_edge_km) + " km" : "—"],
      ["Science proxy", pct(s.science_proxy)],
      ["Thermal proxy", pct(s.thermal_proxy)],
      ["Data coverage", pct(s.data_coverage_fraction)],
      ["Solar power", pct(s.solar_power)],
      ["Earth visibility (scored)", pct(s.earth_visibility)],
      ["Terrain safety", pct(s.terrain_safety)],
      ["ISRU access proxy", pct(s.isru_access_proxy)],
      ["Crew safety", pct(s.crew_safety)],
      ["Data maturity", pct(s.data_maturity)],
      ["Weighted sum", num(s.weighted_sum, 4)],
      ["Weighted geo. mean", num(s.weighted_geometric_mean, 4)],
      ["Hard failures", esc(s.hard_failures || "—")],
      ["Disqualified", s.disqualified ? "Yes" : "No"],
      ["Status", esc(s.status)],
      ["Hazard certified", s.hazard_certified ? "Yes" : "No"],
      ["Required data", esc(s.required_data)],
    ];
    return `<dl class="dx-dl">${rows
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
      .join("")}</dl>`;
  }

  function renderRefinement() {
    const r = D.refinement;
    const rows = [
      ["Stage-1 cell size", r.stage1_cell_size_m != null ? r.stage1_cell_size_m + " m" : "—"],
      ["Stage-2 source resolution", r.stage2_source_resolution_m != null ? num(r.stage2_source_resolution_m) + " m" : "—"],
      ["Horizon", r.horizon_km != null ? r.horizon_km + " km" : "—"],
      ["Azimuth bins", int(r.azimuth_bins)],
      ["Pinpoint status", esc(r.pinpoint_status)],
    ];
    return `<dl class="dx-dl">${rows
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
      .join("")}</dl>`;
  }

  function renderWeights() {
    const w = D.recommendation.weights;
    const items = Object.keys(w).map((key) => {
      const label = key.replace(/([A-Z])/g, " $1").replace(/\b\w/g, (c) => c.toUpperCase());
      const value = w[key];
      return `<li><span class="label">${esc(label)}</span><output class="value count" data-count-to="${value}" data-count-fmt="pct">0%</output></li>`;
    });
    return `<ul class="dx-list">${items.join("")}</ul>`;
  }

  function renderRegions() {
    const regions = D.regions || [];
    if (!regions.length) return "<em>no regions</em>";
    return regions
      .map((region, i) => {
        const inner = renderObject(region, { maxDepth: 2 });
        return `<section class="dx-card reveal stagger-child"><h3>Region ${i + 1}</h3><dl class="dx-dl dx-compact">${inner}</dl></section>`;
      })
      .join("");
  }

  function renderScoring() {
    const s = D.scoring || {};
    const rows = [
      ["Headline", esc(s.headline)],
      ["Geometric floor", s.geometric_floor != null ? num(s.geometric_floor) : "—"],
    ];
    const policy = s.policy;
    let policyHtml = "";
    if (policy) {
      policyHtml = `<dt class="dx-group">Policy</dt><dd><dl class="dx-dl dx-compact">${renderObject(policy)}</dl></dd>`;
    }
    return `<dl class="dx-dl">${rows
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`)
      .join("")}${policyHtml}</dl>`;
  }

  function renderArtifacts() {
    const artifacts = D.artifacts || [];
    if (!artifacts.length) return "<em>no artifacts</em>";
    return artifacts
      .map((a) => {
        const label =
          typeof a === "object" && a !== null ? (a.label || a.path || "") : esc(String(a));
        const path =
          typeof a === "object" && a !== null ? a.path : "";
        const bytesText =
          typeof a === "object" && a !== null && a.bytes != null ? bytes(a.bytes) : "";
        return `<div class="dx-artifact"><a class="name count" href="${esc(path)}" target="_blank" rel="noopener">${esc(label)}</a><span class="size">${esc(bytesText)}</span></div>`;
      })
      .join("");
  }

  function renderLimits() {
    const items = [
      "Coordinate is a provisional source-pixel seed, not a landing pad.",
      "5 m Barker/LOLA LDEM or 1\u20132 m LROC NAC stereo DTM with error layer still required.",
      "NASA data are used for independent analysis; NASA does not endorse this product.",
      "Horizon modelled to a 5 km radius; terrain beyond is unresolved.",
      "Result is screening only, not flight certification.",
    ];
    return `<ul class="dx-list">${items
      .map((t) => `<li><span class="label">Limit</span><span class="value">${esc(t)}</span></li>`)
      .join("")}</ul>`;
  }

  /* ----------------------------------------------------------------------
     Render count values
     ---------------------------------------------------------------------- */
  function formatCount(value, fmt) {
    if (!Number.isFinite(value)) return "—";
    if (fmt === "pct") return pct(value);
    if (fmt === "num") return num(value);
    if (fmt === "int") return int(value);
    if (fmt === "bytes") return bytes(value);
    if (fmt === "coord") return String(value);
    return num(value);
  }
  function renderCounts(scope) {
    $$(".count[data-count-to]", scope || document).forEach((el) => {
      if (el.classList.contains("done")) return;
      const format = el.dataset.countFmt || "num";
      el.textContent = formatCount(Number(el.dataset.countTo), format);
      el.classList.add("done");
    });
  }

  /* ----------------------------------------------------------------------
     Reveal animation via IntersectionObserver
     ---------------------------------------------------------------------- */
  function setupReveals() {
    if (REDUCED) {
      $$(".reveal, .stagger-child").forEach((el) => {
        el.classList.add("is-visible");
        el.style.opacity = "1";
        el.style.transform = "none";
      });
      renderCounts(document);
      return;
    }
    if (!("IntersectionObserver" in window)) {
      renderCounts(document);
      return;
    }
    document.documentElement.classList.add("dx-motion");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          el.classList.add("is-visible");
          observer.unobserve(el);
          if (el.classList.contains("stagger-child")) return;
          const children = $$(".stagger-child", el);
          children.forEach((child, i) => {
            child.style.transitionDelay = i * 90 + "ms";
            child.classList.add("is-visible");
          });
          renderCounts(el);
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -10% 0px" }
    );
    $$(".reveal").forEach((el) => observer.observe(el));
    renderCounts(document);
  }

  /* ----------------------------------------------------------------------
     Init
     ---------------------------------------------------------------------- */
  function init() {
    set(".dx-hero-metrics", renderHeroMetrics());
    set("#view-meta", renderMeta());
    set("#view-recommendation", renderRecommendation());
    set("#view-seed", renderSeed());
    set("#view-refinement", renderRefinement());
    set("#view-weights", renderWeights());
    set("#view-regions", renderRegions());
    set("#view-scoring", renderScoring());
    set("#view-artifacts", renderArtifacts());
    set("#view-limits", renderLimits());
    const footer = $("#dx-footer-meta");
    if (footer && D.meta) {
      footer.textContent =
        "Generated " + stamp(D.meta.generated_at) + " \u00b7 " + int(D.meta.cell_count) + " cells screened";
    }
    setupReveals();
    setupThemeSwitcher();
  }

  /* ----------------------------------------------------------------------
     Theme Switcher & Starry Cosmos Background
     ---------------------------------------------------------------------- */
  function setupThemeSwitcher() {
    const toggle = $("#theme-toggle");
    const themeLabel = $("#theme-label");
    const canvas = $("#starry-canvas");
    if (!toggle || !canvas) return;

    const ctx = canvas.getContext("2d");
    let animId = null;
    let stars = [];
    const STAR_COLORS = ["#f3cdc8", "#f8af99", "#ffffff", "#e79198", "#ffd5cc"];

    function initStars() {
      const w = (canvas.width = window.innerWidth);
      const h = (canvas.height = window.innerHeight);
      const count = Math.min(220, Math.floor((w * h) / 7500));
      stars = [];
      for (let i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          radius: Math.random() * 1.5 + 0.35,
          color: STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)],
          baseAlpha: Math.random() * 0.65 + 0.25,
          twinkleSpeed: Math.random() * 0.035 + 0.008,
          phase: Math.random() * Math.PI * 2,
          hasFlare: Math.random() < 0.12,
        });
      }
    }

    function renderStars() {
      if (document.documentElement.getAttribute("data-theme") !== "dark") {
        if (animId) cancelAnimationFrame(animId);
        animId = null;
        return;
      }
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < stars.length; i++) {
        const s = stars[i];
        s.phase += s.twinkleSpeed;
        const alpha = s.baseAlpha + Math.sin(s.phase) * 0.35;
        const clampedAlpha = Math.max(0.08, Math.min(1, alpha));

        ctx.fillStyle = s.color;
        ctx.globalAlpha = clampedAlpha;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
        ctx.fill();

        if (s.hasFlare && clampedAlpha > 0.6) {
          ctx.strokeStyle = s.color;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(s.x - s.radius * 3.5, s.y);
          ctx.lineTo(s.x + s.radius * 3.5, s.y);
          ctx.moveTo(s.x, s.y - s.radius * 3.5);
          ctx.lineTo(s.x, s.y + s.radius * 3.5);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
      animId = requestAnimationFrame(renderStars);
    }

    function applyTheme(theme) {
      if (theme === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
        toggle.setAttribute("aria-pressed", "true");
        if (themeLabel) themeLabel.textContent = "Light";
        initStars();
        if (!animId) renderStars();
      } else {
        document.documentElement.removeAttribute("data-theme");
        toggle.setAttribute("aria-pressed", "false");
        if (themeLabel) themeLabel.textContent = "Dark";
        if (animId) {
          cancelAnimationFrame(animId);
          animId = null;
        }
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      try {
        localStorage.setItem("lunaria-theme", theme);
      } catch (_) {}
    }

    toggle.addEventListener("click", function () {
      const current = document.documentElement.getAttribute("data-theme");
      applyTheme(current === "dark" ? "light" : "dark");
    });

    window.addEventListener("resize", function () {
      if (document.documentElement.getAttribute("data-theme") === "dark") {
        initStars();
      }
    });

    const saved = localStorage.getItem("lunaria-theme");
    if (saved === "dark") {
      applyTheme("dark");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

