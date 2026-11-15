(function () {
  "use strict";

  const D = window.LUNARIA_POLAR_DATA;
  if (!D) {
    const main = document.querySelector("main");
    if (main) {
      main.innerHTML =
        '<section class="section"><h1>Dashboard data missing</h1><p>Run <code translate="no">python3 scripts/build_polar_dashboard.py</code> to generate <code translate="no">web/data.js</code>.</p></section>';
    }
    return;
  }

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) =>
    Array.prototype.slice.call((root || document).querySelectorAll(selector));
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TAU = Math.PI * 2;

  /* ---------------------------------------------------------------------
     Formatting
     --------------------------------------------------------------------- */

  const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const decimalCache = new Map();

  function decimalFmt(digits) {
    if (!decimalCache.has(digits)) {
      decimalCache.set(
        digits,
        new Intl.NumberFormat("en-US", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        })
      );
    }
    return decimalCache.get(digits);
  }

  function int(value) {
    const number = Number(value);
    return Number.isFinite(number) ? intFmt.format(number) : "—";
  }

  function num(value, digits) {
    const number = Number(value);
    const places = digits == null ? 2 : digits;
    return Number.isFinite(number) ? decimalFmt(places).format(number) : "—";
  }

  function pct(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return num(number * 100, digits == null ? 1 : digits) + "%";
  }

  function signed(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return (number < 0 ? "−" : "+") + num(Math.abs(number), digits == null ? 2 : digits);
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

  const stampFmt = new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hourCycle: "h23",
  });
  const dateFmt = new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const monthFmt = new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });

  function stamp(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || "—") : stampFmt.format(date) + "\u00a0UTC";
  }

  function shortDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || "—") : dateFmt.format(date);
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[character];
    });
  }

  function yesNo(value) {
    return value ? "Yes" : "No";
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function debounce(fn, wait) {
    let timer = 0;
    return function () {
      const args = arguments;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  /* ---------------------------------------------------------------------
     Static maps and constants
     --------------------------------------------------------------------- */

  const DIMENSIONS = D.dimensions;
  const DIM_META = {
    solar_power: { label: "Solar power", note: "illumination utility" },
    earth_visibility: { label: "Earth visibility", note: "graded, not filtered" },
    terrain_safety: { label: "Terrain safety", note: "regional slope proxy" },
    isru_access: { label: "ISRU access", note: "PSR-edge proxy" },
    science_value: { label: "Science", note: "neutral placeholder" },
    thermal_stability: { label: "Thermal", note: "latitude proxy" },
  };

  const REGION_COLORS = ["#0b3d91", "#a33b2d", "#b97c18", "#1d6b67", "#6b5b6e", "#5c6b3f"];
  const LAYER_GRADIENTS = {
    score: "linear-gradient(90deg,#181a3a 0%,#8b7468 50%,#fece96 100%)",
    solar: "linear-gradient(90deg,#221448 0%,#906c33 50%,#ffc51e 100%)",
    earth: "linear-gradient(90deg,#141c3c 0%,#41769e 50%,#6ed0ff 100%)",
    slope: "linear-gradient(90deg,#2dbe5f 0%,#967844 50%,#ff3228 100%)",
  };

  const MAP_HALF_M = 304000;
  const MAP_PX = 608;
  const MOON_RADIUS_M = 1737400;

  const regionById = new Map(D.regions.map(function (region) {
    return [region.region_id, region];
  }));
  const winner =
    regionById.get(D.recommendation.winner) || D.regions[0];
  const regionOrder = new Map(D.regions.map(function (region, index) {
    return [region.region_id, index];
  }));

  function project(latDeg, lonDeg) {
    const lat = (Number(latDeg) * Math.PI) / 180;
    const lon = (Number(lonDeg) * Math.PI) / 180;
    const rho = 2 * MOON_RADIUS_M * Math.tan(Math.PI / 4 + lat / 2);
    const x = rho * Math.sin(lon);
    const y = rho * Math.cos(lon);
    return {
      x: ((x + MAP_HALF_M) / (MAP_HALF_M * 2)) * 100,
      y: ((MAP_HALF_M - y) / (MAP_HALF_M * 2)) * 100,
    };
  }

  function regionCentroid(region) {
    const cells = region.stage1_cells || [];
    if (!cells.length) {
      return project(region.seed.lat_deg, region.seed.lon_deg);
    }
    let row = 0;
    let col = 0;
    cells.forEach(function (cell) {
      row += cell[0] + 0.5;
      col += cell[1] + 0.5;
    });
    row /= cells.length;
    col /= cells.length;
    return { x: (col / MAP_PX) * 100, y: (row / MAP_PX) * 100 };
  }

  /* ---------------------------------------------------------------------
     State and URL
     --------------------------------------------------------------------- */

  function baselineWeights() {
    const values = {};
    DIMENSIONS.forEach(function (key) {
      values[key] = Math.round(D.weights[key] * 100);
    });
    return values;
  }

  const state = {
    layer: "score",
    regionId: winner.region_id,
    index: 0,
    rawWeights: baselineWeights(),
    tab: "validation",
  };

  (function readUrl() {
    try {
      const params = new URLSearchParams(window.location.search);
      const layer = params.get("layer");
      if (layer && D.layers[layer]) state.layer = layer;
      const region = params.get("region");
      if (region && regionById.has(region)) state.regionId = region;
      const index = Number(params.get("t"));
      if (Number.isInteger(index) && index >= 0 && index < D.timestamps.length) {
        state.index = index;
      }
      const weights = params.get("w");
      if (weights) {
        const values = weights.split(",").map(Number);
        if (
          values.length === DIMENSIONS.length &&
          values.every(function (value) {
            return Number.isFinite(value) && value >= 0;
          })
        ) {
          DIMENSIONS.forEach(function (key, position) {
            state.rawWeights[key] = values[position];
          });
        }
      }
      const tab = params.get("tab");
      if (tab && ["validation", "gaps", "artifacts", "policy"].indexOf(tab) !== -1) {
        state.tab = tab;
      }
    } catch (error) {
      /* A malformed query string simply falls back to defaults. */
    }
  })();

  let urlTimer = 0;

  function scheduleUrl() {
    if (urlTimer) return;
    urlTimer = window.setTimeout(function () {
      urlTimer = 0;
      syncUrl();
    }, 180);
  }

  function syncUrl() {
    try {
      const params = new URLSearchParams();
      if (state.layer !== "score") params.set("layer", state.layer);
      if (state.regionId !== winner.region_id) params.set("region", state.regionId);
      if (state.index > 0) params.set("t", String(state.index));
      if (state.tab !== "validation") params.set("tab", state.tab);
      const base = baselineWeights();
      const raw = DIMENSIONS.map(function (key) {
        return Math.round(state.rawWeights[key]);
      });
      const changed = DIMENSIONS.some(function (key, index) {
        return Math.abs(raw[index] - base[key]) > 0.01;
      });
      if (changed) params.set("w", raw.join(","));
      const query = params.toString();
      const next =
        window.location.pathname + (query ? "?" + query : "") + window.location.hash;
      window.history.replaceState(null, "", next);
    } catch (error) {
      /* History can be restricted under file:// in some browsers. */
    }
  }

  /* ---------------------------------------------------------------------
     Reveal and count helpers
     --------------------------------------------------------------------- */

  function countSpan(value, digits, suffix) {
    const text = num(Number(value), digits == null ? 0 : digits) + (suffix || "");
    return (
      '<span class="count">' +
      esc(text) +
      "</span>"
    );
  }

  /* ---------------------------------------------------------------------
     Hero
     --------------------------------------------------------------------- */

  function renderHero() {
    const seed = winner.seed;
    $("#hero-coordinate").textContent = coordLat(seed.lat_deg);
    $("#hero-cell-count").textContent = int(D.meta.cell_count);
    $("#hero-seed-coordinate").innerHTML =
      esc(coordLat(seed.lat_deg)) + "<br>" + esc(coordLon(seed.lon_deg));

    const metrics = [
      {
        value: D.meta.cell_count,
        digits: 0,
        suffix: "",
        label: "1\u00a0km cells screened",
      },
      {
        value: D.meta.refined_cell_count,
        digits: 0,
        suffix: "",
        label: "refined source cells",
      },
      {
        value: winner.weighted_geometric_mean * 100,
        digits: 2,
        suffix: "",
        label: "winning score / 100",
      },
      {
        value: winner.top1_probability * 100,
        digits: 1,
        suffix: "%",
        label: "top-1 under weight draws",
      },
    ];

    $("#hero-metrics").innerHTML = metrics
      .map(function (metric) {
        return (
          '<div class="hero-metric"><dt>' +
          esc(metric.label) +
          '</dt><dd class="metric-value">' +
          countSpan(metric.value, metric.digits, metric.suffix) +
          "</dd></div>"
        );
      })
      .join("");

    const markers = D.regions
      .map(function (region, index) {
        const point = regionCentroid(region);
        const classes =
          "map-marker" +
          (region.region_id === winner.region_id ? " is-winner" : "");
        return (
          '<span class="' +
          classes +
          '" style="--x:' +
          point.x.toFixed(3) +
          "%;--y:" +
          point.y.toFixed(3) +
          "%;--i:" +
          index +
          '"><span class="marker-ring"></span>' +
          (region.region_id === winner.region_id
            ? '<span class="marker-label">R' + region.rank + "</span>"
            : "") +
          "</span>"
        );
      })
      .join("");

    const seedPoint = project(seed.lat_deg, seed.lon_deg);
    const seedMarker =
      '<span class="seed-marker" style="--x:' +
      seedPoint.x.toFixed(3) +
      "%;--y:" +
      seedPoint.y.toFixed(3) +
      '%"><span class="seed-label">seed</span></span>';

    $("#hero-overlay").innerHTML = markers + seedMarker;

  }

  /* ---------------------------------------------------------------------
     Pipeline
     --------------------------------------------------------------------- */

  function renderPipeline() {
    $("#pipeline").innerHTML = D.pipeline
      .map(function (step, index) {
        return (
          "<li>" +
          '<span class="step-num">' +
          String(index + 1).padStart(2, "0") +
          "</span>" +
          '<span class="step-value">' +
          countSpan(step.value, 0, "") +
          "</span>" +
          '<span class="step-unit">' +
          esc(step.unit) +
          "</span>" +
          '<span class="step-label">' +
          esc(step.label) +
          "</span>" +
          '<span class="step-detail">' +
          esc(step.detail) +
          "</span>" +
          "</li>"
        );
      })
      .join("");
  }

  /* ---------------------------------------------------------------------
     Result
     --------------------------------------------------------------------- */

  function renderResult() {
    $("#winner-score").textContent = num(winner.weighted_geometric_mean * 100, 2);
    $("#winner-top1").textContent = pct(winner.top1_probability, 1);

    const ranked = DIMENSIONS.map(function (key) {
      return { key: key, value: winner.dimensions[key] };
    }).sort(function (a, b) {
      return b.value - a.value;
    });
    const strongest = ranked[0];
    const weakest = ranked[ranked.length - 1];
    const seed = winner.seed;

    $("#winner-summary").textContent =
      winner.label +
      " leads the refined screen at " +
      num(winner.weighted_geometric_mean * 100, 2) +
      "/100. Its strongest utility is " +
      DIM_META[strongest.key].label.toLowerCase() +
      " (" +
      num(strongest.value * 100, 1) +
      "); its weakest is " +
      DIM_META[weakest.key].label.toLowerCase() +
      " (" +
      num(weakest.value * 100, 1) +
      "). At the seed cell, " +
      pct(seed.solar_fraction, 2) +
      " of samples are sunlit and " +
      pct(seed.earth_fraction, 2) +
      " have direct Earth visibility.";

    $("#indicator-ledger").innerHTML = DIMENSIONS.map(function (key) {
      const meta = DIM_META[key];
      const value = winner.dimensions[key];
      return (
        '<div class="ledger-row">' +
        '<div class="ledger-name">' +
        esc(meta.label) +
        '<span class="ledger-tag">' +
        esc(meta.note) +
        "</span></div>" +
        '<div class="ledger-bar" aria-hidden="true"><i style="--v:' +
        value.toFixed(6) +
        '"></i></div>' +
        '<span class="ledger-weight">' +
        Math.round(D.weights[key] * 100) +
        "%</span>" +
        '<span class="ledger-value">' +
        num(value * 100, 1) +
        "</span></div>"
      );
    }).join("");

    $("#seed-coordinate").innerHTML =
      esc(coordLat(seed.lat_deg)) + "<br>" + esc(coordLon(seed.lon_deg));
    $("#seed-region").textContent =
      winner.label +
      " · refined rank " +
      winner.rank +
      " of " +
      D.regions.length +
      " · stage-one rank " +
      winner.stage1_rank;

    const seedFacts = [
      ["Seed score", num(seed.score * 100, 2) + " / 100"],
      ["Solar illumination", pct(seed.solar_fraction, 2)],
      ["Earth visibility", pct(seed.earth_fraction, 2)],
      ["Longest dark period", num(seed.longest_dark_days, 2) + "\u00a0d"],
      ["Regional slope p90", num(seed.slope_p90_deg, 2) + "°"],
      ["PSR edge distance", num(seed.psr_edge_km, 2) + "\u00a0km"],
      ["Elevation", num(seed.elevation_m, 2) + "\u00a0m"],
      ["Source resolution", num(seed.resolution_m, 2) + " m/px"],
    ];
    $("#seed-facts").innerHTML = seedFacts
      .map(function (fact) {
        return (
          '<div class="seed-fact"><dt>' +
          esc(fact[0]) +
          "</dt><dd>" +
          esc(fact[1]) +
          "</dd></div>"
        );
      })
      .join("");

    $("#ranking-method").textContent =
      "Weighted geometric mean of six independent dimensions; stage-one rank is shown for context.";

    const headers = [
      "#",
      "Region",
      "Stage 1",
      "Cells",
      "Solar",
      "Earth",
      "Terrain",
      "ISRU",
      "Science",
      "Thermal",
      "Score",
      "Top-1",
      "",
    ];
    const rows = D.regions
      .map(function (region) {
        const dimensionCells = DIMENSIONS.map(function (key) {
          const value = region.dimensions[key];
          return (
            '<td title="' +
            esc(DIM_META[key].label + " utility: " + num(value * 100, 2) + " of 100") +
            '">' +
            num(value * 100, 0) +
            "</td>"
          );
        }).join("");
        return (
          '<tr data-region="' +
          esc(region.region_id) +
          '">' +
          "<td>" +
          region.rank +
          "</td>" +
          '<td class="region-cell"><span class="region-code">R' +
          region.rank +
          "</span>" +
          esc(region.label) +
          "</td>" +
          '<td><span class="stage-rank">' +
          region.stage1_rank +
          "</span></td>" +
          "<td>" +
          int(region.eligible_cell_count) +
          "</td>" +
          dimensionCells +
          '<td class="score-cell">' +
          num(region.weighted_geometric_mean * 100, 2) +
          "</td>" +
          "<td>" +
          pct(region.top1_probability, 1) +
          "</td>" +
          '<td><button type="button" class="inspect-button" data-region="' +
          esc(region.region_id) +
          '" aria-label="Inspect ' +
          esc(region.label) +
          ' in the atlas">Inspect</button></td>' +
          "</tr>"
        );
      })
      .join("");

    $("#region-table").innerHTML =
      '<table class="region-data">' +
      '<caption class="visually-hidden">Refined candidate regions with all six weighted utilities, score, and top-1 sensitivity.</caption>' +
      "<thead><tr>" +
      headers
        .map(function (header) {
          return '<th scope="col">' + esc(header) + "</th>";
        })
        .join("") +
      "</tr></thead><tbody>" +
      rows +
      "</tbody></table>";
  }

  /* ---------------------------------------------------------------------
     Atlas layers and region selection
     --------------------------------------------------------------------- */

  let layerToken = 0;

  function renderLayerSwitch() {
    const order = ["score", "solar", "earth", "slope"];
    $("#layer-switch").innerHTML = order
      .map(function (key) {
        const layer = D.layers[key];
        return (
          '<button type="button" class="layer-button" data-layer="' +
          key +
          '" aria-pressed="' +
          (key === state.layer ? "true" : "false") +
          '">' +
          esc(layer.label) +
          "</button>"
        );
      })
      .join("");

    $$("#layer-switch .layer-button").forEach(function (button) {
      button.addEventListener("click", function () {
        setLayer(button.dataset.layer);
      });
    });
  }

  function updateLayerCaption(key) {
    const layer = D.layers[key];
    if (!layer) return;
    $("#layer-label").textContent = layer.label;
    $("#layer-description").textContent = layer.description;
    $("#legend-low").textContent = layer.low;
    $("#legend-high").textContent = layer.high;
    const legend = $(".legend");
    if (legend) legend.style.setProperty("--legend-gradient", LAYER_GRADIENTS[key]);
    $$("#layer-switch .layer-button").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.layer === key ? "true" : "false");
    });
  }

  function setLayer(key, options) {
    const settings = options || {};
    if (!D.layers[key]) return;
    const changed = settings.force || state.layer !== key;
    state.layer = key;
    updateLayerCaption(key);
    if (settings.updateUrl !== false) scheduleUrl();
    if (!changed) return;

    const imageA = $("#atlas-image");
    const imageB = $("#atlas-ghost");
    if (!imageA || !imageB) return;
    const visible = imageA.classList.contains("is-visible") ? imageA : imageB;
    const incoming = visible === imageA ? imageB : imageA;
    const token = ++layerToken;
    const layer = D.layers[key];
    const alt = layer.label + ". " + layer.description;

    incoming.loading = "eager";
    incoming.src = layer.src;
    incoming.alt = alt;
    incoming.removeAttribute("aria-hidden");

    function apply() {
      if (token !== layerToken) return;
      incoming.classList.add("is-visible");
      visible.classList.remove("is-visible");
      visible.setAttribute("aria-hidden", "true");
      visible.alt = "";
    }

    if (settings.animate === false || REDUCED) {
      apply();
      return;
    }
    if (incoming.complete) {
      window.requestAnimationFrame(apply);
    } else {
      incoming.addEventListener("load", function () {
        window.requestAnimationFrame(apply);
      }, { once: true });
    }
  }

  function markerButton(region) {
    const point = regionCentroid(region);
    const classes =
      "map-marker" +
      (region.region_id === state.regionId ? " is-selected" : "") +
      (region.region_id === winner.region_id ? " is-winner" : "");
    return (
      '<button type="button" class="' +
      classes +
      '" data-region="' +
      esc(region.region_id) +
      '" aria-pressed="' +
      (region.region_id === state.regionId ? "true" : "false") +
      '" aria-label="Inspect ' +
      esc(region.label) +
      ' on the atlas map" style="--x:' +
      point.x.toFixed(3) +
      "%;--y:" +
      point.y.toFixed(3) +
      '"><span class="marker-ring"></span><span class="marker-label">R' +
      region.rank +
      "</span></button>"
    );
  }

  function renderAtlas() {
    renderLayerSwitch();

    $("#region-switch").innerHTML = D.regions
      .map(function (region) {
        return (
          '<button type="button" class="region-button" data-region="' +
          esc(region.region_id) +
          '" aria-pressed="' +
          (region.region_id === state.regionId ? "true" : "false") +
          '" aria-label="Show ' +
          esc(region.label) +
          ' in the inspector"><b>R' +
          region.rank +
          "</b><span>" +
          num(region.weighted_geometric_mean * 100, 1) +
          "</span></button>"
        );
      })
      .join("");

    $("#atlas-overlay").innerHTML =
      D.regions.map(markerButton).join("") +
      '<span class="seed-marker" id="atlas-seed" aria-hidden="true"><span class="seed-label">Seed</span></span>';

    $$("#region-switch .region-button").forEach(function (button) {
      button.addEventListener("click", function () {
        selectRegion(button.dataset.region);
      });
    });

    $("#atlas-overlay").addEventListener("click", function (event) {
      const button = event.target.closest(".map-marker");
      if (button) selectRegion(button.dataset.region);
    });

    $("#region-table").addEventListener("click", function (event) {
      const button = event.target.closest(".inspect-button");
      if (button) selectRegion(button.dataset.region, { scroll: true });
    });

    if (state.layer !== "score") {
      setLayer(state.layer, { animate: false, updateUrl: false, force: true });
    } else {
      updateLayerCaption("score");
    }
  }

  function renderInspector() {
    const region = regionById.get(state.regionId) || winner;
    const stats = D.region_stats[region.region_id];
    const seed = region.seed;
    const relation =
      region.stage1_rank > region.rank
        ? "promoted from stage-one rank " + region.stage1_rank
        : region.stage1_rank < region.rank
        ? "slipped from stage-one rank " + region.stage1_rank
        : "held stage-one rank " + region.stage1_rank;

    const statRows = [
      ["Cells eligible", int(region.eligible_cell_count) + " / " + int(region.cell_count)],
      ["Solar median", pct(stats.solar.median, 1)],
      ["Earth median", pct(stats.earth.median, 1)],
      ["Slope median", num(stats.slope.median, 2) + "°"],
      ["Dark median", num(stats.dark.median, 1) + "\u00a0d"],
      ["PSR edge median", num(stats.psr.median, 2) + "\u00a0km"],
    ];

    $("#region-insight").innerHTML =
      '<p class="insight-kicker">Refined rank ' +
      region.rank +
      " of " +
      D.regions.length +
      " · " +
      esc(relation) +
      "</p>" +
      '<h3 class="insight-title">' +
      esc(region.label) +
      "</h3>" +
      '<p class="insight-score">' +
      num(region.weighted_geometric_mean * 100, 1) +
      "<span>/100 · top-1 " +
      pct(region.top1_probability, 1) +
      "</span></p>" +
      '<dl class="insight-stats">' +
      statRows
        .map(function (row) {
          return (
            '<div class="insight-stat"><dt>' +
            esc(row[0]) +
            "</dt><dd>" +
            esc(row[1]) +
            "</dd></div>"
          );
        })
        .join("") +
      "</dl>" +
      '<p class="insight-seed"><strong>Seed ' +
      esc(coord(seed.lat_deg, seed.lon_deg)) +
      "</strong><br>Seed score " +
      num(seed.score * 100, 2) +
      "/100 · " +
      pct(seed.solar_fraction, 2) +
      " sunlit · " +
      pct(seed.earth_fraction, 2) +
      " Earth-visible</p>";

    const scatter = $("#refined-scatter");
    if (scatter) {
      scatter.setAttribute(
        "aria-label",
        "Scatter plot of 1,206 refined cells: Earth visibility on the horizontal axis and solar illumination on the vertical axis. " +
          region.label +
          " is highlighted; its seed is marked with a ring."
      );
    }
  }

  function applyRegionSelection(options) {
    const settings = options || {};
    const region = regionById.get(state.regionId) || winner;

    $$("#region-table tbody tr").forEach(function (row) {
      row.classList.toggle("is-selected", row.dataset.region === state.regionId);
    });
    $$("#region-switch .region-button").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.region === state.regionId ? "true" : "false");
    });
    $$("#atlas-overlay .map-marker").forEach(function (button) {
      const selected = button.dataset.region === state.regionId;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    const seedMarker = $("#atlas-seed");
    if (seedMarker) {
      const point = project(region.seed.lat_deg, region.seed.lon_deg);
      seedMarker.style.setProperty("--x", point.x.toFixed(3) + "%");
      seedMarker.style.setProperty("--y", point.y.toFixed(3) + "%");
      seedMarker.title = "Provisional seed " + coord(region.seed.lat_deg, region.seed.lon_deg);
    }

    renderInspector();
    updateStatus(true);
    drawScatter();
    drawTimelineFrame();

    if (settings.scroll) {
      const atlas = $("#atlas");
      if (atlas) {
        atlas.scrollIntoView({
          behavior: REDUCED ? "auto" : "smooth",
          block: "start",
        });
      }
    }
  }

  function selectRegion(regionId, options) {
    if (!regionById.has(regionId)) return;
    state.regionId = regionId;
    applyRegionSelection(options);
    scheduleUrl();
  }

  /* ---------------------------------------------------------------------
     Refined-cell scatter
     --------------------------------------------------------------------- */

  const scatterCanvas = $("#refined-scatter");
  const scatterProgress = 1;

  function fitCanvas(canvas, width, height) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.height = height + "px";
    const context = canvas.getContext("2d");
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    return context;
  }

  function drawScatter() {
    if (!scatterCanvas) return;
    const width = Math.max(250, scatterCanvas.parentElement.clientWidth || 320);
    const height = Math.round(clamp(width * 0.63, 230, 320));
    const context = fitCanvas(scatterCanvas, width, height);
    const margin = { left: 38, right: 12, top: 20, bottom: 32 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const selectedIndex = regionOrder.get(state.regionId);
    const region = regionById.get(state.regionId) || winner;
    const color = REGION_COLORS[region.rank - 1] || "#0b3d91";
    const progress = clamp(scatterProgress, 0, 1);

    context.clearRect(0, 0, width, height);
    context.font = '10px "IBM Plex Mono", monospace';
    context.textAlign = "center";
    context.textBaseline = "middle";

    const ticks = [0, 0.25, 0.5, 0.75, 1];
    const labelStep = plotWidth < 300 ? 0.5 : 0.25;

    ticks.forEach(function (tick) {
      const x = margin.left + tick * plotWidth;
      const y = margin.top + (1 - tick) * plotHeight;
      context.strokeStyle = "rgba(23,25,27,0.10)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x + 0.5, margin.top);
      context.lineTo(x + 0.5, margin.top + plotHeight);
      context.stroke();
      context.beginPath();
      context.moveTo(margin.left, y + 0.5);
      context.lineTo(margin.left + plotWidth, y + 0.5);
      context.stroke();
      if (Math.abs(tick / labelStep - Math.round(tick / labelStep)) < 0.001) {
        context.fillStyle = "#5b5a54";
        context.fillText(Math.round(tick * 100) + "%", x, margin.top + plotHeight + 13);
        context.textAlign = "right";
        context.fillText(Math.round(tick * 100) + "%", margin.left - 7, y);
        context.textAlign = "center";
      }
    });

    context.strokeStyle = "rgba(23,25,27,0.35)";
    context.beginPath();
    context.moveTo(margin.left + 0.5, margin.top);
    context.lineTo(margin.left + 0.5, margin.top + plotHeight);
    context.lineTo(margin.left + plotWidth, margin.top + plotHeight);
    context.stroke();

    const rows = D.refined_cells.rows;
    context.globalAlpha = progress;

    rows.forEach(function (row) {
      if (row[0] === selectedIndex) return;
      const x = margin.left + row[2] * plotWidth;
      const y = margin.top + (1 - row[1]) * plotHeight;
      context.fillStyle = "rgba(23,25,27,0.16)";
      context.fillRect(x - 1, y - 1, 2, 2);
    });

    rows.forEach(function (row) {
      if (row[0] !== selectedIndex) return;
      const x = margin.left + row[2] * plotWidth;
      const y = margin.top + (1 - row[1]) * plotHeight;
      context.beginPath();
      context.arc(x, y, 2.1, 0, TAU);
      context.fillStyle = color;
      context.globalAlpha = progress * 0.82;
      context.fill();
    });

    const seed = region.seed;
    const seedX = margin.left + seed.earth_fraction * plotWidth;
    const seedY = margin.top + (1 - seed.solar_fraction) * plotHeight;
    context.globalAlpha = progress;
    context.strokeStyle = "#7d540d";
    context.lineWidth = 1.5;
    context.beginPath();
    context.arc(seedX, seedY, 5, 0, TAU);
    context.stroke();
    context.beginPath();
    context.moveTo(seedX - 8, seedY);
    context.lineTo(seedX + 8, seedY);
    context.moveTo(seedX, seedY - 8);
    context.lineTo(seedX, seedY + 8);
    context.stroke();

    context.globalAlpha = 1;
    context.fillStyle = "#5b5a54";
    context.textAlign = "center";
    context.fillText("Earth visibility", margin.left + plotWidth / 2, height - 7);
    context.save();
    context.translate(10, margin.top + plotHeight / 2);
    context.rotate(-Math.PI / 2);
    context.fillText("Solar illumination", 0, 0);
    context.restore();
  }

  /* ---------------------------------------------------------------------
     Cell distributions
     --------------------------------------------------------------------- */

  const DIST_CONFIG = [
    {
      key: "score",
      title: "Suitability score",
      color: "#0b3d91",
      format: function (value) { return pct(value, 1); },
      axis: function (value) { return pct(value, 0); },
    },
    {
      key: "solar",
      title: "Solar illumination",
      color: "#b97c18",
      format: function (value) { return pct(value, 1); },
      axis: function (value) { return pct(value, 0); },
    },
    {
      key: "earth",
      title: "Earth visibility",
      color: "#1d6b67",
      format: function (value) { return pct(value, 1); },
      axis: function (value) { return pct(value, 0); },
    },
    {
      key: "slope",
      title: "Regional slope p90",
      color: "#a33b2d",
      format: function (value) { return num(value, 1) + "°"; },
      axis: function (value) { return num(value, 0) + "°"; },
    },
    {
      key: "dark",
      title: "Longest dark period",
      color: "#5b5a54",
      format: function (value) { return num(value, 1) + "\u00a0d"; },
      axis: function (value) { return num(value, 0) + "\u00a0d"; },
    },
    {
      key: "psr",
      title: "PSR edge distance",
      color: "#6b5b6e",
      format: function (value) { return num(value, 1) + "\u00a0km"; },
      axis: function (value) { return num(value, 0) + "\u00a0km"; },
    },
  ];

  const distProgress = new Map();

  function renderDistributions() {
    $("#distributions").innerHTML = DIST_CONFIG.map(function (config) {
      const stats = D.cell_stats[config.key];
      const clipped =
        stats.clipped > 0
          ? '<p class="dist-clip">' +
            int(stats.clipped) +
            " samples outside " +
            esc(config.axis(stats.low)) +
            "–" +
            esc(config.axis(stats.high)) +
            "</p>"
          : "";
      return (
        '<article class="dist-card" data-dist="' +
        config.key +
        '">' +
        '<div class="dist-head"><h4>' +
        esc(config.title) +
        '</h4><span class="dist-sub">n ' +
        int(stats.count) +
        " · " +
        stats.bins.length +
        " bins</span></div>" +
        '<canvas class="dist-canvas" id="dist-' +
        config.key +
        '" width="300" height="118" role="img" aria-label="Histogram of ' +
        esc(config.title.toLowerCase()) +
        ' across ' +
        int(stats.count) +
        " screened cells. Median " +
        esc(config.format(stats.median)) +
        ", 10th to 90th percentile " +
        esc(config.format(stats.p10)) +
        " to " +
        esc(config.format(stats.p90)) +
        '."></canvas>' +
        '<dl class="dist-stats">' +
        "<div class=\"dist-stat\"><dt>Median</dt><dd>" +
        esc(config.format(stats.median)) +
        "</dd></div>" +
        "<div class=\"dist-stat\"><dt>p10–p90</dt><dd>" +
        esc(config.format(stats.p10)) +
        " – " +
        esc(config.format(stats.p90)) +
        "</dd></div>" +
        "<div class=\"dist-stat\"><dt>Max</dt><dd>" +
        esc(config.format(stats.max)) +
        "</dd></div>" +
        "</dl>" +
        clipped +
        "</article>"
      );
    }).join("");

    DIST_CONFIG.forEach(function (config) {
      distProgress.set(config.key, 1);
      drawDistribution(config.key, 1);
    });
  }

  function drawDistribution(key, progress) {
    const config = DIST_CONFIG.find(function (item) { return item.key === key; });
    const canvas = $("#dist-" + key);
    if (!config || !canvas) return;
    const stats = D.cell_stats[key];
    const card = canvas.closest(".dist-card");
    const width = Math.max(220, canvas.clientWidth || (card ? card.clientWidth - 32 : 280));
    const height = 118;
    const context = fitCanvas(canvas, width, height);
    const margin = { left: 7, right: 7, top: 9, bottom: 19 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const maximum = Math.max.apply(null, stats.bins.concat([1]));
    const bins = stats.bins.length;
    const step = plotWidth / bins;
    const barGap = Math.min(2, step * 0.18);
    const eased = clamp(progress == null ? 1 : progress, 0, 1);

    context.clearRect(0, 0, width, height);

    context.strokeStyle = "rgba(23,25,27,0.14)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(margin.left, margin.top + plotHeight + 0.5);
    context.lineTo(margin.left + plotWidth, margin.top + plotHeight + 0.5);
    context.stroke();

    stats.bins.forEach(function (count, index) {
      if (!count) return;
      const barHeight = (count / maximum) * plotHeight * eased;
      const x = margin.left + index * step;
      const y = margin.top + plotHeight - barHeight;
      context.fillStyle = config.color;
      context.globalAlpha = 0.82;
      context.fillRect(x + barGap / 2, y, Math.max(1, step - barGap), barHeight);
    });
    context.globalAlpha = 1;

    const medianPosition =
      (stats.median - stats.low) / Math.max(1e-9, stats.high - stats.low);
    if (medianPosition >= 0 && medianPosition <= 1) {
      const x = margin.left + medianPosition * plotWidth;
      context.strokeStyle = "rgba(23,25,27,0.55)";
      context.setLineDash([3, 3]);
      context.beginPath();
      context.moveTo(x + 0.5, margin.top);
      context.lineTo(x + 0.5, margin.top + plotHeight);
      context.stroke();
      context.setLineDash([]);
    }

    context.font = '9px "IBM Plex Mono", monospace';
    context.fillStyle = "#5b5a54";
    context.textBaseline = "top";
    context.textAlign = "left";
    context.fillText(config.axis(stats.low), margin.left, margin.top + plotHeight + 5);
    context.textAlign = "right";
    context.fillText(
      config.axis(stats.high),
      margin.left + plotWidth,
      margin.top + plotHeight + 5
    );
  }

  /* ---------------------------------------------------------------------
     Sun/Earth timeline
     --------------------------------------------------------------------- */

  const TIMELINE = {
    canvas: $("#timeline-canvas"),
    slider: $("#timeline"),
    date: $("#timeline-date"),
    announce: $("#timeline-announcer"),
    button: $("#play-timeline"),
    base: document.createElement("canvas"),
    geometry: null,
    baseKey: "",
    progress: 1,
    playing: false,
    raf: 0,
    lastTs: 0,
    accumulator: 0,
  };

  function monthTicks() {
    const stamps = D.timestamps;
    const start = new Date(stamps[0]);
    const end = new Date(stamps[stamps.length - 1]);
    const stepMs = D.meta.step_hours * 60 * 60 * 1000;
    const ticks = [];
    let cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
    if (cursor < start) {
      cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
    }
    while (cursor <= end) {
      const index = Math.round((cursor.getTime() - start.getTime()) / stepMs);
      if (index >= 0 && index < stamps.length) {
        ticks.push({ index: index, label: monthFmt.format(cursor) });
      }
      cursor = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1));
    }
    return ticks;
  }

  function alphaPalette(red, green, blue) {
    const palette = [];
    for (let index = 0; index <= 100; index += 1) {
      const alpha = (0.12 + 0.88 * (index / 100)).toFixed(3);
      palette.push("rgba(" + red + "," + green + "," + blue + "," + alpha + ")");
    }
    return palette;
  }

  function buildTimelineBase(geometry) {
    const base = TIMELINE.base;
    const dpr = geometry.dpr;
    base.width = Math.round(geometry.width * dpr);
    base.height = Math.round(geometry.height * dpr);
    const context = base.getContext("2d");
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.fillStyle = "#14181c";
    context.fillRect(0, 0, geometry.width, geometry.height);

    const left = geometry.left;
    const top = geometry.top;
    const plotWidth = geometry.plotWidth;
    const rowHeight = geometry.rowHeight;
    const samples = D.timestamps.length;
    const sunPalette = alphaPalette(224, 173, 79);
    const earthPalette = alphaPalette(102, 201, 193);

    context.font = '9px "IBM Plex Mono", monospace';
    context.textAlign = "left";
    context.textBaseline = "middle";
    context.fillStyle = "#8f999a";
    context.fillText(
      geometry.width < 560
        ? "Sun / Earth availability · " + int(D.meta.timeline_rows) + " samples"
        : "Sun and direct Earth availability · " +
            int(D.meta.timeline_rows) +
            " aligned six-hour samples",
      left,
      12
    );

    D.regions.forEach(function (region, regionIndex) {
      const rowY = top + regionIndex * rowHeight;
      const selected = region.region_id === state.regionId;
      if (selected) {
        context.fillStyle = "rgba(255,255,255,0.05)";
        context.fillRect(0, rowY, geometry.width, rowHeight);
        context.fillStyle = "#dfa945";
        context.fillRect(0, rowY, 3, rowHeight);
      }

      context.font = selected
        ? '500 10px "IBM Plex Mono", monospace'
        : '10px "IBM Plex Mono", monospace';
      context.fillStyle = selected ? "#f1ecdf" : "#a9b2b2";
      context.textAlign = "right";
      context.fillText("R" + region.rank, left - 12, rowY + rowHeight / 2);

      const bandHeight = Math.min(12, (rowHeight - 13) / 2);
      const sunY = rowY + 4;
      const earthY = sunY + bandHeight + 4;
      context.fillStyle = "#20262a";
      context.fillRect(left, sunY, plotWidth, bandHeight);
      context.fillRect(left, earthY, plotWidth, bandHeight);

      const series = D.timeline[region.region_id];
      const columns = Math.ceil(plotWidth);
      for (let column = 0; column < columns; column += 1) {
        const start = Math.floor((column / plotWidth) * samples);
        const end = Math.max(
          start + 1,
          Math.min(samples, Math.floor(((column + 1) / plotWidth) * samples))
        );
        let sunVisible = 0;
        let earthVisible = 0;
        for (let sample = start; sample < end; sample += 1) {
          if (series[sample][2]) sunVisible += 1;
          if (series[sample][5]) earthVisible += 1;
        }
        const span = end - start;
        if (sunVisible) {
          const shade = Math.round((sunVisible / span) * 100);
          context.fillStyle = sunPalette[shade];
          context.fillRect(left + column, sunY, 1, bandHeight);
        }
        if (earthVisible) {
          const shade = Math.round((earthVisible / span) * 100);
          context.fillStyle = earthPalette[shade];
          context.fillRect(left + column, earthY, 1, bandHeight);
        }
      }

      context.fillStyle = "rgba(255,255,255,0.08)";
      context.fillRect(left, rowY + rowHeight - 0.5, plotWidth, 0.5);
    });

    const ticks = monthTicks();
    const tickEvery = plotWidth < 620 ? 6 : 3;
    context.font = '8px "IBM Plex Mono", monospace';
    context.textAlign = "center";
    ticks.forEach(function (tick, tickIndex) {
      if (tickIndex % tickEvery !== 0 && tickIndex !== ticks.length - 1) return;
      const x = left + (tick.index / (samples - 1)) * plotWidth;
      context.strokeStyle = "rgba(255,255,255,0.10)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x + 0.5, top - 2);
      context.lineTo(x + 0.5, geometry.height - geometry.bottom + 2);
      context.stroke();
      context.fillStyle = "#8f999a";
      context.textAlign =
        x > left + plotWidth - 16
          ? "right"
          : x < left + 16
          ? "left"
          : "center";
      context.fillText(tick.label, x, geometry.height - 8);
    });
    context.textAlign = "center";
  }

  function ensureTimeline() {
    if (!TIMELINE.canvas) return null;
    const width = Math.max(
      300,
      TIMELINE.canvas.clientWidth ||
        TIMELINE.canvas.parentElement.clientWidth - 14
    );
    const height = 300;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const key = [width, height, dpr, state.regionId].join("|");
    if (TIMELINE.geometry && TIMELINE.baseKey === key) {
      return TIMELINE.geometry;
    }
    const left = 78;
    const right = 10;
    const top = 26;
    const bottom = 24;
    const geometry = {
      width: width,
      height: height,
      dpr: dpr,
      left: left,
      right: right,
      top: top,
      bottom: bottom,
      plotWidth: width - left - right,
      rowHeight: (height - top - bottom) / D.regions.length,
    };
    TIMELINE.canvas.width = Math.round(width * dpr);
    TIMELINE.canvas.height = Math.round(height * dpr);
    TIMELINE.canvas.style.height = height + "px";
    TIMELINE.geometry = geometry;
    TIMELINE.baseKey = key;
    buildTimelineBase(geometry);
    return geometry;
  }

  function drawTimelineFrame() {
    const geometry = ensureTimeline();
    if (!geometry) return;
    const context = TIMELINE.canvas.getContext("2d");
    context.setTransform(geometry.dpr, 0, 0, geometry.dpr, 0, 0);
    context.clearRect(0, 0, geometry.width, geometry.height);
    context.fillStyle = "#14181c";
    context.fillRect(0, 0, geometry.width, geometry.height);

    const progress = clamp(TIMELINE.progress, 0, 1);
    if (progress > 0) {
      const sourceWidth = Math.max(1, Math.round(TIMELINE.base.width * progress));
      const destinationWidth = Math.max(1, geometry.width * progress);
      context.drawImage(
        TIMELINE.base,
        0,
        0,
        sourceWidth,
        TIMELINE.base.height,
        0,
        0,
        destinationWidth,
        geometry.height
      );
    }

    const samples = D.timestamps.length;
    const x =
      geometry.left +
      (samples <= 1 ? 0 : (state.index / (samples - 1)) * geometry.plotWidth);
    if (x <= geometry.left + geometry.plotWidth * progress + 0.5) {
      context.strokeStyle = "#f1ecdf";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x + 0.5, geometry.top - 2);
      context.lineTo(x + 0.5, geometry.height - geometry.bottom + 2);
      context.stroke();
      context.fillStyle = "#f1ecdf";
      context.beginPath();
      context.arc(x, geometry.top - 4, 2.4, 0, TAU);
      context.fill();
    }
  }

  let lastStatusUpdate = 0;

  function statusCell(visible, elevation, horizon, kind) {
    const label = visible ? "Above" : "Below";
    const className = visible
      ? kind === "sun"
        ? "status-sun-above"
        : "status-above"
      : "status-below";
    const title =
      label +
      " terrain horizon. Elevation " +
      signed(elevation) +
      "; horizon " +
      signed(horizon) +
      ".";
    return (
      '<span class="status-badge ' +
      className +
      '" title="' +
      esc(title) +
      '"><i class="status-dot" aria-hidden="true"></i><span>' +
      label +
      '</span><span class="status-angle">' +
      signed(elevation) +
      " / " +
      signed(horizon) +
      "</span></span>"
    );
  }

  function updateStatus(force) {
    const now = window.performance.now();
    if (!force && now - lastStatusUpdate < 70) return;
    lastStatusUpdate = now;
    const rows = $$("#status-body tr");
    rows.forEach(function (row) {
      const regionId = row.dataset.region;
      const series = D.timeline[regionId];
      if (!series) return;
      const sample = series[state.index];
      const sunCell = row.querySelector(".sun-cell");
      const earthCell = row.querySelector(".earth-cell");
      if (sunCell) sunCell.innerHTML = statusCell(sample[2], sample[0], sample[1], "sun");
      if (earthCell) {
        earthCell.innerHTML = statusCell(sample[5], sample[3], sample[4], "earth");
      }
      row.classList.toggle("is-selected", regionId === state.regionId);
    });
  }

  function announceTimeline() {
    if (!TIMELINE.announce) return;
    const region = regionById.get(state.regionId) || winner;
    const sample = D.timeline[region.region_id][state.index];
    TIMELINE.announce.textContent =
      stamp(D.timestamps[state.index]) +
      ". " +
      region.label +
      ": Sun " +
      (sample[2] ? "above" : "below") +
      " terrain; Earth " +
      (sample[5] ? "above" : "below") +
      " terrain.";
  }

  function setTimelineIndex(index, options) {
    const settings = options || {};
    const maximum = D.timestamps.length - 1;
    state.index = clamp(Math.round(index), 0, maximum);
    if (TIMELINE.slider) TIMELINE.slider.value = String(state.index);
    if (TIMELINE.date) TIMELINE.date.textContent = stamp(D.timestamps[state.index]);
    drawTimelineFrame();
    updateStatus(settings.force);
    if (settings.url !== false) scheduleUrl();
    if (settings.announce) announceTimeline();
  }

  function stopPlayback(announce) {
    if (!TIMELINE.playing) return;
    TIMELINE.playing = false;
    if (TIMELINE.raf) window.cancelAnimationFrame(TIMELINE.raf);
    TIMELINE.raf = 0;
    if (TIMELINE.button) {
      TIMELINE.button.setAttribute("aria-pressed", "false");
      TIMELINE.button.textContent = "Play Timeline";
    }
    scheduleUrl();
    if (announce) announceTimeline();
  }

  function playbackStep(now) {
    if (!TIMELINE.playing) return;
    const elapsed = Math.max(0, now - TIMELINE.lastTs);
    TIMELINE.lastTs = now;
    TIMELINE.accumulator += elapsed * 0.11;
    const maximum = D.timestamps.length - 1;
    if (TIMELINE.accumulator >= maximum) {
      setTimelineIndex(maximum, { url: false });
      stopPlayback(true);
      return;
    }
    setTimelineIndex(Math.floor(TIMELINE.accumulator), { url: false });
    TIMELINE.raf = window.requestAnimationFrame(playbackStep);
  }

  function startPlayback() {
    if (TIMELINE.playing) {
      stopPlayback(true);
      return;
    }
    const maximum = D.timestamps.length - 1;
    if (state.index >= maximum) setTimelineIndex(0, { url: false, force: true });
    TIMELINE.playing = true;
    TIMELINE.accumulator = state.index;
    TIMELINE.lastTs = window.performance.now();
    if (TIMELINE.button) {
      TIMELINE.button.setAttribute("aria-pressed", "true");
      TIMELINE.button.textContent = "Pause Timeline";
    }
    TIMELINE.raf = window.requestAnimationFrame(playbackStep);
  }

  function renderSignals() {
    if (!TIMELINE.slider) return;
    TIMELINE.slider.max = String(D.timestamps.length - 1);
    $("#status-body").innerHTML = D.regions
      .map(function (region) {
        return (
          '<tr data-region="' +
          esc(region.region_id) +
          '"><td class="status-region"><span class="region-code">R' +
          region.rank +
          "</span>" +
          esc(region.label) +
          '</td><td class="sun-cell"></td><td class="earth-cell"></td></tr>'
        );
      })
      .join("");

    TIMELINE.slider.addEventListener("input", function () {
      stopPlayback(false);
      setTimelineIndex(Number(TIMELINE.slider.value), { announce: false });
    });
    TIMELINE.slider.addEventListener("change", function () {
      announceTimeline();
      scheduleUrl();
    });
    if (TIMELINE.button) {
      TIMELINE.button.addEventListener("click", startPlayback);
    }

    setTimelineIndex(state.index, { url: false, force: true });
  }

  /* ---------------------------------------------------------------------
     Live weights
     --------------------------------------------------------------------- */

  const liveRows = new Map();

  function renderWeights() {
    $("#weight-controls").innerHTML = DIMENSIONS.map(function (key) {
      const meta = DIM_META[key];
      return (
        '<div class="weight-control">' +
        '<label for="weight-' +
        key +
        '">' +
        esc(meta.label) +
        '<span class="weight-desc">' +
        esc(meta.note) +
        "</span></label>" +
        '<input id="weight-' +
        key +
        '" name="mission-priority-' +
        key +
        '" data-weight="' +
        key +
        '" type="range" min="0" max="100" step="1" autocomplete="off" value="' +
        Math.round(state.rawWeights[key]) +
        '">' +
        '<output class="weight-output" id="weight-out-' +
        key +
        '" for="weight-' +
        key +
        '">0%</output>' +
        "</div>"
      );
    }).join("");

    $("#live-ranking").innerHTML = D.regions
      .map(function (region) {
        return (
          '<div class="live-row" data-region="' +
          esc(region.region_id) +
          '"><span class="live-rank">0</span><div><div class="live-top"><span>' +
          esc(region.label) +
          "</span><output>0.0</output></div>" +
          '<div class="live-bar" aria-hidden="true"><i></i></div></div></div>'
        );
      })
      .join("");

    liveRows.clear();
    $$("#live-ranking .live-row").forEach(function (row) {
      liveRows.set(row.dataset.region, row);
    });

    $("#sensitivity-strip").innerHTML = D.regions
      .map(function (region) {
        return (
          '<div class="sensitivity-row"><span class="sensitivity-label">R' +
          region.rank +
          '</span><div class="sensitivity-track" aria-hidden="true"><i style="--v:' +
          region.top1_probability.toFixed(6) +
          '"></i></div><span class="sensitivity-value">' +
          pct(region.top1_probability, 1) +
          "</span></div>"
        );
      })
      .join("");

    $("#weight-controls").addEventListener("input", function (event) {
      const input = event.target.closest("input[data-weight]");
      if (!input) return;
      state.rawWeights[input.dataset.weight] = Number(input.value);
      updateWeights(true, false);
      scheduleUrl();
    });

    $("#weight-controls").addEventListener("change", function (event) {
      const input = event.target.closest("input[data-weight]");
      if (!input) return;
      state.rawWeights[input.dataset.weight] = Number(input.value);
      updateWeights(false, true);
      scheduleUrl();
    });

    $("#reset-weights").addEventListener("click", function () {
      state.rawWeights = baselineWeights();
      DIMENSIONS.forEach(function (key) {
        const input = $("#weight-" + key);
        if (input) input.value = String(state.rawWeights[key]);
      });
      updateWeights(true, true);
      scheduleUrl();
    });

    updateWeights(false, false);
  }

  function updateWeights(animate, announce) {
    const rawTotal = DIMENSIONS.reduce(function (sum, key) {
      return sum + Math.max(0, Number(state.rawWeights[key]) || 0);
    }, 0);
    const normalized = {};
    DIMENSIONS.forEach(function (key) {
      normalized[key] =
        rawTotal > 0
          ? Math.max(0, Number(state.rawWeights[key]) || 0) / rawTotal
          : 1 / DIMENSIONS.length;
      const input = $("#weight-" + key);
      const output = $("#weight-out-" + key);
      if (output) output.textContent = pct(normalized[key], 0);
      if (input) {
        input.setAttribute(
          "aria-valuetext",
          Math.round(Number(state.rawWeights[key]) || 0) +
            " priority; " +
            pct(normalized[key], 0) +
            " normalized"
        );
      }
    });

    const floor = Number(D.scoring.geometric_floor) || 0.01;
    const scores = {};
    D.regions.forEach(function (region) {
      const logScore = DIMENSIONS.reduce(function (sum, key) {
        return sum + normalized[key] * Math.log(Math.max(region.dimensions[key], floor));
      }, 0);
      scores[region.region_id] = Math.exp(logScore);
    });

    const sorted = D.regions.slice().sort(function (a, b) {
      return scores[b.region_id] - scores[a.region_id];
    });

    const shouldAnimate =
      animate &&
      !REDUCED &&
      typeof Element !== "undefined" &&
      Element.prototype.animate;
    const firstPositions = new Map();
    if (shouldAnimate) {
      liveRows.forEach(function (row, regionId) {
        firstPositions.set(regionId, row.getBoundingClientRect().top);
      });
    }

    sorted.forEach(function (region, index) {
      const row = liveRows.get(region.region_id);
      if (!row) return;
      row.querySelector(".live-rank").textContent = String(index + 1);
      row.querySelector(".live-top output").textContent = num(
        scores[region.region_id] * 100,
        1
      );
      row.querySelector(".live-bar i").style.transform =
        "scaleX(" + scores[region.region_id].toFixed(6) + ")";
      row.classList.toggle("is-leader", index === 0);
    });

    sorted.forEach(function (region) {
      const row = liveRows.get(region.region_id);
      if (row) $("#live-ranking").appendChild(row);
    });

    if (shouldAnimate) {
      const lastPositions = new Map();
      sorted.forEach(function (region) {
        const row = liveRows.get(region.region_id);
        if (!row) return;
        lastPositions.set(region.region_id, row.getBoundingClientRect().top);
      });
      sorted.forEach(function (region) {
        const row = liveRows.get(region.region_id);
        if (!row) return;
        const delta = firstPositions.get(region.region_id) - lastPositions.get(region.region_id);
        if (Math.abs(delta) < 0.5) return;
        row.animate(
          [
            { transform: "translateY(" + delta + "px)" },
            { transform: "translateY(0)" },
          ],
          { duration: 420, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" }
        );
      });
    }

    const leader = sorted[0];
    const second = sorted[1];
    let sentence;
    if (second && Math.abs(scores[leader.region_id] - scores[second.region_id]) < 1e-9) {
      sentence =
        leader.label +
        " and " +
        second.label +
        " are tied at " +
        num(scores[leader.region_id] * 100, 1) +
        "/100.";
    } else {
      sentence =
        leader.label +
        " leads at " +
        num(scores[leader.region_id] * 100, 1) +
        "/100 under the current priorities.";
    }
    $("#weight-winner").textContent = sentence;
    if (announce) $("#weight-live").textContent = sentence;
  }

  /* ---------------------------------------------------------------------
     Evidence
     --------------------------------------------------------------------- */

  function renderValidation() {
    const benchmark = D.benchmark;
    const projection = benchmark.projection_round_trip;
    const sun = benchmark.horizons_geometry_cross_check;
    const earth = benchmark.horizons_earth_geometry_cross_check;
    const consistency = benchmark.scoring_consistency;
    const distribution = benchmark.illumination_distribution;
    const legacy = benchmark.legacy_comparison || [];
    const barker = D.recommendation.barker_validation;
    const artemis = D.artemis_regions;

    const legacyRows = legacy
      .map(function (row) {
        return (
          "<li><strong>" +
          esc(row.site_id.replace(/_/g, " ")) +
          "</strong>: model " +
          pct(row.model_illumination, 2) +
          " vs legacy " +
          pct(row.legacy_reported, 2) +
          ", nearest-cell offset " +
          num(row.offset_km, 2) +
          "\u00a0km. " +
          esc(row.note) +
          ".</li>"
        );
      })
      .join("");

    const chips = artemis.regions
      .map(function (region) {
        return '<li class="chip">' + esc(region.name) + "</li>";
      })
      .join("");

    $("#panel-validation").innerHTML =
      '<h3 class="visually-hidden">Validation results</h3>' +
      '<div class="validation-grid">' +
      '<article class="check-card"><div class="check-head"><h4>Projection round-trip</h4><span class="status-pill is-pass">Pass</span></div><p class="check-value">' +
      num(projection.max_round_trip_error_m, 4) +
      ' <small>m max error</small></p><p class="check-meta">' +
      int(projection.samples) +
      " samples · Moon 2000 south-polar stereographic.</p></article>" +
      '<article class="check-card"><div class="check-head"><h4>Sun geometry</h4><span class="status-pill is-pass">Pass</span></div><p class="check-value">' +
      num(sun.max_elevation_diff_deg, 5) +
      '° <small>max Δ elevation</small></p><p class="check-meta">Δ azimuth ' +
      num(sun.max_azimuth_diff_deg, 5) +
      "° · " +
      int(sun.samples) +
      " samples · vs JPL Horizons.</p></article>" +
      '<article class="check-card"><div class="check-head"><h4>Earth geometry</h4><span class="status-pill is-pass">Pass</span></div><p class="check-value">' +
      num(earth.max_elevation_diff_deg, 5) +
      '° <small>max Δ elevation</small></p><p class="check-meta">Δ azimuth ' +
      num(earth.max_azimuth_diff_deg, 5) +
      "° · " +
      int(earth.samples) +
      " samples · vs JPL Horizons.</p></article>" +
      '<article class="check-card"><div class="check-head"><h4>Scoring consistency</h4><span class="status-pill">Diagnostic</span></div><p class="check-value">ρ ' +
      num(consistency.spearman_rho, 4) +
      ' <small>rank correlation</small></p><p class="check-meta">' +
      int(consistency.sample) +
      " sampled cells · geometric mean vs weighted sum · top-500 overlap " +
      pct(consistency.top500_overlap, 1) +
      " · mean gap " +
      num(consistency.mean_absolute_gap, 4) +
      ".</p></article>" +
      '<article class="check-card is-wide"><div class="check-head"><h4>Full-cell screen</h4><span class="status-pill">' +
      int(distribution.cells) +
      ' cells</span></div><p class="check-value">' +
      pct(distribution.illumination.median, 1) +
      ' <small>median solar</small></p><p class="check-meta">Earth median ' +
      pct(distribution.earth_visibility.median, 1) +
      " · longest dark median " +
      num(distribution.longest_dark_days.median, 1) +
      " d · valid coverage median " +
      pct(distribution.data_coverage.median, 0) +
      ".</p></article>" +
      '<article class="check-card is-blocked"><div class="check-head"><h4>Barker et al. 5&nbsp;m validation</h4><span class="status-pill is-blocked">Blocked</span></div><p class="check-value">No pass result claimed</p><p class="check-meta">' +
      esc(barker.reason) +
      " Exact Barker ROI LDEMs, error layers, and valid-pixel masks are required before this check can run.</p></article>" +
      "</div>" +
      '<div class="validation-extra">' +
      "<section><h4>Geometry method</h4><ul class=\"method-list\">" +
      "<li>Sub-solar and sub-Earth points are evaluated in the Moon body-fixed frame with surface parallax, then compared against a topocentric Horizons observer at <code translate=\"no\">89.9°S, 0°E</code>.</li>" +
      "<li>Ephemeris: <code translate=\"no\">" +
      int(D.meta.timeline_rows / D.regions.length) +
      "</code> six-hour samples per region, spanning " +
      esc(shortDate(D.meta.window_start)) +
      " to " +
      esc(shortDate(D.meta.window_end)) +
      ".</li>" +
      "<li>Horizons rays use 96 azimuth bins to 60&nbsp;km; the highest ~148&nbsp;m source pixel in each 1&nbsp;km cell is the optimistic observer.</li>" +
      "<li>Projection: Moon 2000 south-polar stereographic, 608 × 608&nbsp;km at 1&nbsp;km cells.</li>" +
      "</ul></section>" +
      '<section><h4>Archived site cross-check</h4><ul class="legacy-list">' +
      legacyRows +
      "</ul></section>" +
      '<section><h4>Artemis III candidate regions</h4><p class="artemis-note">Official candidate-region polygons are <strong>' +
      esc(artemis.geometry_status) +
      "</strong>, so Lunaria does not intersect this result with Artemis III. The " +
      artemis.regions.length +
      " named regions are listed only as context.</p><ul class=\"chip-list\">" +
      chips +
      '</ul><p class="artemis-note"><a href="' +
      esc(artemis.source_url) +
      '" target="_blank" rel="noopener noreferrer">NASA candidate-region announcement</a></p></section>' +
      '<section><h4>What remains unvalidated</h4><ul class="method-list">' +
      "<li>Metre-scale slope, roughness, boulders, and landing hazards; no certified landing pad exists here.</li>" +
      "<li>5&nbsp;m Barker/LOLA terrain with vertical error and valid-pixel masks.</li>" +
      "<li>Diviner thermal measurements, LEND/Mini-RF volatiles, and relay link budget.</li>" +
      "<li>Artemis III polygon overlap and mission-specific flight certification.</li>" +
      "<li>Science value (fixed 0.50 placeholder) and thermal stability (latitude proxy).</li>" +
      "</ul></section></div>";
  }

  function renderGaps() {
    $("#panel-gaps").innerHTML =
      '<h3 class="visually-hidden">Data gaps</h3>' +
      '<div class="gap-list">' +
      D.data_gaps
        .map(function (gap) {
          const metaRows = [
            ["AOI", gap.aoi],
            ["Desired resolution", gap.desired_resolution],
            ["Request from", gap.request_from],
            ["Status", gap.status],
            ["Placeholder", gap.placeholder_file],
            ["Acceptance", gap.acceptance],
          ]
            .map(function (row) {
              return (
                "<div><dt>" +
                esc(row[0]) +
                "</dt><dd>" +
                esc(row[1]) +
                "</dd></div>"
              );
            })
            .join("");
          return (
            '<article class="gap-item"><span class="priority-badge' +
            (gap.priority === "P1" ? " is-p1" : "") +
            '">' +
            esc(gap.priority) +
            '</span><div class="gap-body"><div class="gap-top"><h4>' +
            esc(gap.dataset) +
            '</h4><span class="gap-id">' +
            esc(gap.gap_id) +
            "</span></div><p class=\"gap-why\">" +
            esc(gap.why) +
            '</p><dl class="gap-meta">' +
            metaRows +
            '</dl><p class="gap-request"><strong>Request:</strong> ' +
            esc(gap.request_spec) +
            "</p></div></article>"
          );
        })
        .join("") +
      "</div>";
  }

  function renderArtifacts() {
    const totalBytes = D.artifacts.reduce(function (sum, artifact) {
      return sum + (Number(artifact.bytes) || 0);
    }, 0);
    const rows = D.artifacts
      .map(function (artifact) {
        return (
          "<tr><td><a href=\"" +
          esc(artifact.href) +
          '" download>' +
          esc(artifact.label) +
          '</a><span class="artifact-path">' +
          esc(artifact.path) +
          "</span></td><td><span class=\"kind-tag\">" +
          esc(artifact.kind) +
          "</span></td><td>" +
          (artifact.rows == null ? "—" : int(artifact.rows)) +
          "</td><td>" +
          bytes(artifact.bytes) +
          '</td><td><code class="hash" translate="no" title="' +
          esc(artifact.sha256) +
          '">' +
          esc(artifact.sha256.slice(0, 12)) +
          "…</code></td></tr>"
        );
      })
      .join("");

    $("#panel-artifacts").innerHTML =
      '<h3 class="visually-hidden">Generated artifacts</h3>' +
      '<div class="artifact-intro"><p><strong>' +
      D.artifacts.length +
      " tracked files</strong> · " +
      bytes(totalBytes) +
      " · SHA-256 checksums copied from <code translate=\"no\">polar_data_manifest.json</code>. Links are relative to the repository root.</p></div>" +
      '<div class="artifact-table-wrap" role="region" tabindex="0" aria-label="Tracked processed artifacts table"><table class="artifact-table"><caption class="visually-hidden">Tracked processed artifacts</caption><thead><tr><th scope="col">Artifact</th><th scope="col">Kind</th><th scope="col">Rows</th><th scope="col">Size</th><th scope="col">SHA-256</th></tr></thead><tbody>' +
      rows +
      '</tbody></table></div><p class="scroll-hint" aria-hidden="true">Scroll the table to inspect every artifact and checksum →</p>';
  }

  const UTILITY_LABELS = {
    solar_illumination: "Solar illumination",
    longest_dark_period: "Longest dark period",
    sunlight_continuity: "Sunlight continuity",
    earth_visibility: "Earth visibility",
    regional_terrain_roughness: "Regional terrain roughness",
    pinpoint_slope: "Pinpoint slope",
    isru_access: "ISRU access",
    science_value: "Science value",
    thermal_stability: "Thermal stability",
    crew_safety: "Crew safety",
    data_maturity: "Data maturity",
  };

  function utilityRule(key, utility) {
    if (key === "solar_illumination") {
      return "Linear: 0 at " + pct(utility.low, 0) + ", 1 at " + pct(utility.high, 0) + ".";
    }
    if (key === "longest_dark_period") {
      return "Linear: 1 at " + num(utility.low_days, 1) + "&nbsp;d, 0 at " + num(utility.high_days, 1) + "&nbsp;d.";
    }
    if (key === "sunlight_continuity") {
      return "Report only; not weighted. Mission-window continuity is not folded into the headline.";
    }
    if (key === "earth_visibility") {
      return "Linear: 0 at " + pct(utility.low, 0) + ", 1 at " + pct(utility.high, 0) + "; never a hard filter.";
    }
    if (key === "regional_terrain_roughness") {
      return "1 below " + num(utility.full_below, 1) + "°; 0 above " + num(utility.zero_above, 1) + "°.";
    }
    if (key === "pinpoint_slope") {
      return "1 below " + num(utility.full_below, 1) + "°; 0 above " + num(utility.zero_above, 1) + "°.";
    }
    if (key === "isru_access") {
      return "exp(−distance / " + num(utility.scale_km, 1) + "&nbsp;km) to a mapped PSR edge.";
    }
    if (key === "science_value") {
      return "Fixed at 0.50 until an independent geology or spectral layer is ingested.";
    }
    if (key === "thermal_stability") {
      return "1 at 90°S, decreasing linearly to 0 at 80°S.";
    }
    if (key === "crew_safety") {
      return "Alias of terrain safety; not weighted a second time.";
    }
    if (key === "data_maturity") {
      return "Valid-pixel coverage of the exported raster; report-only, not a mission utility.";
    }
    return esc(utility.type || "");
  }

  function definitionList(rows) {
    return (
      '<dl class="policy-dl">' +
      rows
        .map(function (row) {
          return "<dt>" + esc(row[0]) + "</dt><dd>" + row[1] + "</dd>";
        })
        .join("") +
      "</dl>"
    );
  }

  function renderPolicy() {
    const policy = D.policy;
    const scope = policy.scope;
    const assumptions = policy.assumptions;
    const scoring = policy.scoring;
    const validation = policy.validation;
    const barker = D.recommendation.barker_validation;

    const scopeList = definitionList([
      ["Latitude band", num(scope.latitude_min_deg, 0) + "° to " + num(scope.latitude_max_deg, 0) + "°"],
      ["Target cell", int(scope.target_cell_size_m) + "&nbsp;m"],
      ["Fine DEM", esc(scope.fine_dem_source)],
      ["Pinpoint DEMs", scope.pinpoint_dem_sources.map(esc).join("<br>")],
      ["Policy version", esc(policy.version)],
    ]);

    const assumptionList = definitionList([
      ["Slope p90 limit", num(assumptions.slope_p90_limit_deg, 1) + "° (configurable assumption)"],
      ["Solar minimum", pct(assumptions.solar_illumination_min_fraction, 0)],
      ["Slope threshold", esc(assumptions.slope_threshold_type)],
      ["Solar threshold", esc(assumptions.solar_threshold_type)],
      ["Earth hard filter", "No — visibility is graded, not disqualifying"],
      ["Relay availability", esc(assumptions.relay_availability)],
    ]);

    const scoringList = definitionList([
      ["Headline", "Weighted geometric mean of six independent dimensions"],
      ["Geometric floor", num(scoring.geometric_floor, 2)],
      ["Weighted sum", yesNo(scoring.weighted_sum)],
      ["Sensitivity", esc(scoring.sensitivity_method).replace(/\.\.\./g, "…") + " · " + int(scoring.sensitivity_draws) + " draws · seed " + int(scoring.random_seed)],
      ["Cluster rule", int(scoring.cluster_connectivity) + "-connected · cell score ≥ " + num(scoring.cluster_cell_score_min, 2) + " · minimum " + int(scoring.cluster_min_cells) + " cells"],
      ["Continuity", "Report-only; not part of the headline"],
      ["Cluster note", esc(scoring.cluster_selection_note)],
    ]);

    const weightList = definitionList(
      DIMENSIONS.map(function (key) {
        return [DIM_META[key].label, pct(policy.weights[key], 0)];
      })
    );

    const validationList = definitionList([
      ["Reference", esc(validation.reference)],
      ["Reference window", esc(validation.reference_window_start) + " to " + esc(validation.reference_window_end)],
      ["Reference site", esc(validation.reference_site)],
      ["Expected ranking", esc(validation.expected_ranking)],
      ["Pass rule", esc(validation.pass_rule)],
      ["Current status", esc(barker.status) + " — " + esc(barker.reason)],
    ]);

    const utilityRows = Object.keys(policy.utilities)
      .map(function (key) {
        const utility = policy.utilities[key];
        const note = utility.description || utility.label || "";
        return (
          "<tr><td>" +
          esc(UTILITY_LABELS[key] || key) +
          (note ? '<span class="utility-note">' + esc(note) + "</span>" : "") +
          "</td><td>" +
          esc(utility.type) +
          "</td><td>" +
          utilityRule(key, utility) +
          "</td></tr>"
        );
      })
      .join("");

    $("#panel-policy").innerHTML =
      '<h3 class="visually-hidden">Scoring policy</h3>' +
      '<div class="policy-grid">' +
      '<section class="policy-section"><h4>Scope</h4><p>Operational bounds for the two-stage screen. The context is a screening product, not a flight certification.</p>' +
      scopeList +
      "</section>" +
      '<section class="policy-section"><h4>Assumptions</h4><p>Thresholds are configurable assumptions. The 15° slope limit applies to fine-resolution pinpoint slope when it exists; this run has only the regional proxy.</p>' +
      assumptionList +
      "</section>" +
      '<section class="policy-section"><h4>Scoring</h4><p>The geometric mean punishes any weak dimension rather than letting a strong dimension hide it. The floor prevents a zero utility from collapsing the product.</p>' +
      scoringList +
      "</section>" +
      '<section class="policy-section"><h4>Baseline weights</h4><p>These are the headline weights fixed before the weight-draw sensitivity test.</p>' +
      weightList +
      "</section>" +
      '<section class="policy-section"><h4>Validation policy</h4><p>The Barker check is explicitly blocked rather than approximated.</p>' +
      validationList +
      "</section>" +
      "</div>" +
      '<section class="policy-section policy-utilities"><h4>Utility definitions</h4><p>Every transformation used by the score, including the values that are report-only or deliberately not weighted.</p><table class="utility-table"><caption class="visually-hidden">Utility definitions and weights</caption><thead><tr><th scope="col">Utility</th><th scope="col">Type</th><th scope="col">Rule</th></tr></thead><tbody>' +
      utilityRows +
      "</tbody></table></section>";
  }

  function selectTab(key, options) {
    const settings = options || {};
    const keys = ["validation", "gaps", "artifacts", "policy"];
    if (keys.indexOf(key) === -1) return;
    state.tab = key;
    keys.forEach(function (name) {
      const tab = $("#tab-" + name);
      const panel = $("#panel-" + name);
      const selected = name === key;
      if (tab) {
        tab.setAttribute("aria-selected", selected ? "true" : "false");
        tab.setAttribute("tabindex", selected ? "0" : "-1");
      }
      if (panel) panel.hidden = !selected;
    });
    if (settings.url !== false) scheduleUrl();
    if (settings.focus) {
      const active = $("#tab-" + key);
      if (active) active.focus();
    }
  }

  function renderEvidence() {
    renderValidation();
    renderGaps();
    renderArtifacts();
    renderPolicy();

    const tablist = $(".evidence-tabs");
    if (tablist) {
      tablist.addEventListener("click", function (event) {
        const tab = event.target.closest('[role="tab"]');
        if (!tab) return;
        selectTab(tab.id.replace("tab-", ""));
      });
      tablist.addEventListener("keydown", function (event) {
        const tabs = $$(".evidence-tabs [role=tab]");
        const current = tabs.indexOf(document.activeElement);
        if (current === -1) return;
        let next = current;
        if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
        else if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        else return;
        event.preventDefault();
        selectTab(tabs[next].id.replace("tab-", ""), { focus: true });
      });
    }

    selectTab(state.tab, { url: false });
  }

  function renderCaveats() {
    const caveats = D.recommendation.caveats.slice();
    caveats.push(
      "Barker et al. validation is blocked because the exact 5\u00a0m ROI LDEMs, error layers, and valid-pixel masks are absent."
    );
    caveats.push(
      "Artemis III candidate-region polygons are unavailable; no spatial overlap is claimed."
    );
    $("#caveat-list").innerHTML = caveats
      .map(function (caveat) {
        return "<li>" + esc(caveat) + "</li>";
      })
      .join("");
  }

  function renderFooter() {
    $("#footer-meta").textContent =
      "Run " +
      stamp(D.meta.generated_at) +
      " · window " +
      shortDate(D.meta.window_start) +
      "–" +
      shortDate(D.meta.window_end) +
      " · " +
      int(D.meta.cell_count) +
      " cells · " +
      int(D.meta.refined_cell_count) +
      " refined · " +
      D.meta.artifact_count +
      " files (" +
      bytes(D.meta.artifact_bytes) +
      ")";
  }

  /* ---------------------------------------------------------------------
     Navigation and responsive behaviour
     --------------------------------------------------------------------- */

  function setupScrollSpy() {
    if (!("IntersectionObserver" in window)) return;
    const links = $$(".site-nav a");
    const targets = links
      .map(function (link) {
        const section = $(link.getAttribute("href"));
        return section ? { link: link, section: section } : null;
      })
      .filter(Boolean);
    if (!targets.length) return;
    const visible = new Set();
    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        });
        const first = targets.find(function (target) {
          return visible.has(target.section.id);
        });
        links.forEach(function (link) {
          if (first && link === first.link) link.setAttribute("aria-current", "true");
          else link.removeAttribute("aria-current");
        });
      },
      { rootMargin: "-38% 0px -55% 0px", threshold: 0 }
    );
    targets.forEach(function (target) {
      observer.observe(target.section);
    });
  }

  const handleResize = debounce(function () {
    drawScatter();
    DIST_CONFIG.forEach(function (config) {
      drawDistribution(config.key, distProgress.get(config.key) || 1);
    });
    drawTimelineFrame();
  }, 160);

  /* ---------------------------------------------------------------------
     Boot
     --------------------------------------------------------------------- */

  function init() {
    renderHero();
    renderPipeline();
    renderResult();
    renderAtlas();
    renderSignals();
    renderDistributions();
    renderWeights();
    renderEvidence();
    renderCaveats();
    renderFooter();
    applyRegionSelection();

    setupScrollSpy();
    window.addEventListener("resize", handleResize);
  }

  try {
    init();
  } catch (error) {
    if (window.console) window.console.error(error);
    const main = $("main");
    if (main) {
      const notice = document.createElement("p");
      notice.className = "noscript";
      notice.textContent =
        "The atlas renderer hit an error. The processed files and REPORT.md remain available, and the browser console has the details.";
      main.prepend(notice);
    }
  }
})();
