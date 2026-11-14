/* Lunaria dashboard — vanilla JS, no build step. */
(function () {
  "use strict";

  const D = window.LUNARIA_DATA;
  if (!D) {
    document.body.innerHTML =
      '<main style="padding:60px;font-family:sans-serif;color:#e9eefb">' +
      "<h1>Dashboard data missing</h1>" +
      "<p>Run <code>python3 scripts/build_dashboard.py</code> first.</p></main>";
    return;
  }

  const byId = Object.fromEntries(D.sites.map((s) => [s.id, s]));
  const winner = byId[D.recommendation.winner.site_id];
  const runner = byId[D.recommendation.runner_up.site_id];
  const $ = (sel) => document.querySelector(sel);

  const esc = (value) =>
    String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const num = (value, digits = 1) =>
    value == null || Number.isNaN(Number(value))
      ? "—"
      : Number(value).toFixed(digits);

  const pct = (value, digits = 1) =>
    value == null ? "—" : `${Number(value).toFixed(digits)}%`;

  const prob = (value) => {
    if (value == null) return "—";
    const percent = Number(value) * 100;
    if (percent > 0 && percent < 0.005) return "<0.01%";
    return `${percent.toFixed(2)}%`;
  };

  const coord = (lat, lon) => {
    if (lat == null || lon == null) return "—";
    const ns = lat < 0 ? "S" : "N";
    const ew = lon < 0 ? "W" : "E";
    return `${Math.abs(lat).toFixed(4)}°${ns}, ${Math.abs(lon).toFixed(4)}°${ew}`;
  };

  const hours = (value) => {
    if (value == null) return "—";
    return value >= 48
      ? `${Math.round(value / 24)} d`
      : `${Math.round(value)} h`;
  };

  const tierClass = (tier) =>
    `tier tier-${String(tier || "c").toLowerCase()}`;

  const tip = (title, body) =>
    `data-tip-title="${esc(title)}" data-tip-body="${esc(body)}"`;

  const siteName = (id) => (byId[id] ? byId[id].short_name : id);

  /* ---------------------------------------------------------------- hero */
  function renderHero() {
    $("#winner-card").innerHTML = `
      <div class="card-eyebrow"><span>Recommended</span><span>Rank 01</span></div>
      <h2>${esc(winner.name)}</h2>
      <p class="location">${coord(winner.lat, winner.lon)} · ${esc(winner.region)}</p>
      <div class="winner-score-row">
        <div class="score-ring" style="--p:${Math.max(0, Math.min(100, winner.score))}">
          <div><strong>${num(winner.score, 1)}</strong><small>/ 100</small></div>
        </div>
        <div class="winner-score-copy">
          <p><strong>${prob(winner.top1)}</strong> top-1 probability under joint
          weight and score uncertainty.</p>
          <p style="margin-top:6px">${num(winner.score - runner.score, 1)} points
          ahead of ${esc(runner.short_name)}.</p>
        </div>
      </div>
      <div class="mini-metrics">
        <div class="mini-metric"><span>Sun above terrain</span><strong>${pct(winner.solar_pct)}</strong></div>
        <div class="mini-metric"><span>Earth &gt;5°</span><strong>${pct(winner.earth_pct)}</strong></div>
        <div class="mini-metric"><span>Slope p90</span><strong>${num(winner.slope_p90_deg, 1)}°</strong></div>
      </div>`;

    const meta = D.meta;
    $("#hero-footnote").textContent =
      `Ephemeris window ${meta.window_start.slice(0, 10)} → ${meta.window_end.slice(0, 10)} · ` +
      `${meta.ephemeris_rows.toLocaleString()} Sun/Earth samples · ` +
      `NASA/JPL Horizons + NASA Moon Trek + NASA Image Library.`;

    $("#stat-strip").innerHTML = [
      [meta.site_count, "candidate sites"],
      [meta.ephemeris_rows.toLocaleString(), "Sun/Earth samples"],
      [meta.dem_count, "NASA DEM products"],
      [meta.monte_carlo_draws.toLocaleString(), "uncertainty draws"],
      [`${meta.gap_count} / ${meta.p0_count}`, "data gaps / P0"],
    ]
      .map(
        ([value, label]) =>
          `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`
      )
      .join("");
  }

  /* ------------------------------------------------------------- verdict */
  function renderVerdict() {
    const w = winner;
    const r = runner;
    const rec = D.recommendation;
    $("#winner-panel").innerHTML = `
      <span class="medal">Rank 01 · balanced profile</span>
      <h3>${esc(w.name)}</h3>
      <p class="coords">${coord(w.lat, w.lon)} · elevation ${num(w.elevation_m, 0)} m · ${esc(w.dem_label)}</p>
      <div class="verdict-metrics">
        <div class="verdict-metric"><span>Weighted score</span><strong>${num(w.score, 1)}</strong><small>/ 100</small></div>
        <div class="verdict-metric"><span>Solar</span><strong>${pct(w.solar_pct)}</strong><small>of year above terrain</small></div>
        <div class="verdict-metric"><span>Earth &gt;5°</span><strong>${pct(w.earth_pct)}</strong><small>direct-to-Earth</small></div>
        <div class="verdict-metric"><span>Slope p90</span><strong>${num(w.slope_p90_deg, 1)}°</strong><small>DEM screening</small></div>
      </div>
      <p class="verdict-copy">${esc(rec.rationale[0])} <strong>${esc(rec.rationale[1])}</strong>
      ${esc(rec.rationale[3] || "")}</p>`;

    $("#runner-panel").innerHTML = `
      <div>
        <span class="tag">Runner-up · best crewed sortie</span>
        <h3>${esc(r.name)}</h3>
        <div class="runner-score"><strong>${num(r.score, 1)}</strong><span>/ 100 · ${num(w.score - r.score, 1)} behind</span></div>
      </div>
      <ul class="runner-list">
        <li><span>Earth &gt;5° of year</span><strong>${pct(r.earth_pct)}</strong></li>
        <li><span>Longest comms outage</span><strong>${hours(r.earth_outage_h)}</strong></li>
        <li><span>Slope p90</span><strong>${num(r.slope_p90_deg, 1)}°</strong></li>
        <li><span>Data maturity</span><strong>${num(r.criteria.data_maturity.score, 0)} / 100 · ${r.criteria.data_maturity.tier}</strong></li>
        <li><span>ISRU access</span><strong>${num(r.criteria.isru_water_ice.score, 0)} / 100</strong></li>
      </ul>
      <a class="runner-link" href="#terrain">Inspect the Apollo 17 pad →</a>`;

    const wc = w.criteria;
    const rc = r.criteria;
    const sortie = D.profiles.crewed_sortie.ranking.find(
      (row) => row.site_id === r.id
    );
    const costBullets = [
      `Direct-to-Earth link is only ${pct(w.earth_pct)} of the year; the longest outage is ${hours(w.earth_outage_h)}. A relay is mandatory.`,
      `Thermal score is ${num(wc.thermal_stability.score, 0)}/100 (Tier ${wc.thermal_stability.tier}); no Diviner time series was ingested.`,
      `The 30 m/px polar DEM is too coarse for boulder-scale certification; a 1–2 m NAC DTM is a P0 request.`,
    ];
    const whyBullets = [
      `Highest solar availability in the set: ${pct(w.solar_pct)} of the year above the local terrain horizon.`,
      `Flattest credible polar pad: site slope p90 ${num(w.slope_p90_deg, 1)}°, pinpoint p90 ${num(w.pinpoint.slope_p90_deg, 1)}°.`,
      `PSR edge only ${num(w.psr_edge_km, 1)} km away, giving the best polar volatile-access proxy in the set.`,
    ];
    const altBullets = [
      `Apollo 17 scores ${num(r.score, 1)} and wins the low-risk crewed-sortie profile at ${num(sortie ? sortie.score : null, 1)}.`,
      `It has ${pct(r.earth_pct)} Earth visibility, no relay, and Tier A ground truth.`,
      `It gives up polar ISRU (${num(rc.isru_water_ice.score, 0)}/100) and has a 14-day night.`,
    ];
    $("#why-grid").innerHTML = `
      <article class="why-card"><h3>Why Nobile Ridge wins</h3><ul>${whyBullets
        .map((x) => `<li>${esc(x)}</li>`)
        .join("")}</ul></article>
      <article class="why-card warn"><h3>What it costs</h3><ul>${costBullets
        .map((x) => `<li>${esc(x)}</li>`)
        .join("")}</ul></article>
      <article class="why-card alt"><h3>When Apollo 17 wins</h3><ul>${altBullets
        .map((x) => `<li>${esc(x)}</li>`)
        .join("")}</ul></article>`;

    const pin = w.pinpoint;
    $("#pinpoint-banner").innerHTML = `
      <div>
        <p class="eyebrow" style="margin-bottom:8px">The pinpoint candidate</p>
        <h3>${coord(pin.lat, pin.lon)}</h3>
        <p class="pin-note">${num(pin.offset_km * 1000, 0)} m from the supplied
        coordinate, selected by DEM screening for local flatness and a 5 km open
        horizon. Candidate pad only — not a certified landing site.</p>
      </div>
      <div class="pinpoint-figures">
        <div><span>Pad slope p90</span><strong>${num(pin.slope_p90_deg, 1)}°</strong></div>
        <div><span>Open sky &gt;5°</span><strong>${pct((pin.open_sky_frac_5deg || 0) * 100)}</strong></div>
        <div><span>Pad elevation</span><strong>${num(pin.elevation_m, 0)} m</strong></div>
        <div><span>DEM resolution</span><strong>${num(w.dem_res_m, 0)} m/px</strong></div>
      </div>`;
  }

  /* ------------------------------------------------------------- ranking */
  let activeProfile = D.baseline_profile || "baseline";

  function renderProfileTabs() {
    $("#profile-tabs").innerHTML = Object.values(D.profiles)
      .map(
        (p) =>
          `<button class="profile-tab" role="tab" data-profile="${esc(p.id)}"
            aria-selected="${p.id === activeProfile}">${esc(p.label)}</button>`
      )
      .join("");
    document.querySelectorAll(".profile-tab").forEach((button) => {
      button.addEventListener("click", () => selectProfile(button.dataset.profile));
    });
  }

  function selectProfile(profileId, scroll) {
    activeProfile = profileId;
    document.querySelectorAll(".profile-tab").forEach((button) => {
      button.setAttribute(
        "aria-selected",
        String(button.dataset.profile === profileId)
      );
    });
    document.querySelectorAll(".profile-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.profile === profileId);
    });
    renderRanking();
    if (scroll) {
      document.getElementById("ranking").scrollIntoView({ behavior: "smooth" });
    }
  }

  function renderRanking() {
    const profile = D.profiles[activeProfile];
    $("#ranking-title").textContent = profile.label;
    $("#ranking-description").textContent = profile.description;
    const rows = profile.ranking;
    const max = Math.max(...rows.map((row) => row.score), 1);
    $("#ranking-bars").innerHTML = rows
      .map((row) => {
        const site = byId[row.site_id];
        const isWinner = row.rank === 1;
        const right =
          activeProfile === "baseline" && site
            ? prob(site.top1)
            : `Δ ${num(row.delta, 1)}`;
        return `<div class="bar-row ${isWinner ? "winner" : ""}">
          <span class="bar-rank">${String(row.rank).padStart(2, "0")}</span>
          <span class="bar-name" title="${esc(site ? site.name : row.site_id)}">${esc(site ? site.short_name : row.site_id)}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, (row.score / max) * 100)}%"></span></span>
          <span class="bar-score">${num(row.score, 1)}</span>
          <span class="bar-top1">${right}</span>
        </div>`;
      })
      .join("");
    $("#ranking-note").textContent =
      activeProfile === "baseline"
        ? "Bars are weighted scores out of 100. The right-hand column is top-1 probability under joint weight and score uncertainty."
        : "Bars are weighted scores under this profile. Δ is the gap to the profile winner; top-1 probability is reported for the baseline profile only.";
  }

  /* -------------------------------------------------------------- charts */
  function svgWrap(width, height, inner, label) {
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}" preserveAspectRatio="xMidYMid meet">${inner}</svg>`;
  }

  function renderTradeoff() {
    const W = 640;
    const H = 360;
    const m = { l: 118, r: 150, t: 62, b: 30 };
    const plotW = W - m.l - m.r;
    const plotH = H - m.t - m.b;
    const rowH = plotH / D.sites.length;
    const x = (v) => m.l + (Math.max(0, Math.min(100, v)) / 100) * plotW;
    const y = (i) => m.t + i * rowH + rowH / 2;
    let inner = "";
    [0, 25, 50, 75, 100].forEach((v) => {
      inner += `<line x1="${x(v)}" y1="${m.t - 6}" x2="${x(v)}" y2="${m.t + plotH}" stroke="rgba(148,178,224,.12)" stroke-width="1"/>`;
      inner += `<text x="${x(v)}" y="${m.t - 12}" text-anchor="middle" fill="#6f829f" font-size="10">${v}%</text>`;
    });
    inner += `<circle cx="${m.l}" cy="16" r="4" fill="#f2b84b"/><text x="${m.l + 10}" y="20" fill="#8fa1bd" font-size="11">Sun above terrain</text>`;
    inner += `<circle cx="${m.l + 150}" cy="16" r="4" fill="#79aaff"/><text x="${m.l + 160}" y="20" fill="#8fa1bd" font-size="11">Earth &gt;5° above terrain</text>`;

    D.sites
      .slice()
      .sort((a, b) => a.rank - b.rank)
      .forEach((site, i) => {
        const yy = y(i);
        const xs = x(site.solar_pct);
        const xe = x(site.earth_pct);
        inner += `<line x1="${Math.min(xs, xe)}" y1="${yy}" x2="${Math.max(xs, xe)}" y2="${yy}" stroke="rgba(148,178,224,.22)" stroke-width="2"/>`;
        inner += `<circle cx="${xs}" cy="${yy}" r="6" fill="${site.rank === 1 ? "#f2b84b" : "#c9a45b"}" stroke="#0b1321" stroke-width="2"><title>${esc(site.name)}: Sun ${pct(site.solar_pct)}</title></circle>`;
        inner += `<circle cx="${xe}" cy="${yy}" r="6" fill="#79aaff" stroke="#0b1321" stroke-width="2"><title>${esc(site.name)}: Earth ${pct(site.earth_pct)}</title></circle>`;
        inner += `<text x="${m.l - 12}" y="${yy + 4}" text-anchor="end" fill="${site.rank === 1 ? "#f2b84b" : "#e9eefb"}" font-size="12" font-weight="600">${esc(site.short_name)}</text>`;
        inner += `<text x="${W - 122}" y="${yy + 4}" text-anchor="start" fill="#f2b84b" font-size="11">${pct(site.solar_pct)}</text>`;
        inner += `<text x="${W - 52}" y="${yy + 4}" text-anchor="start" fill="#79aaff" font-size="11">${pct(site.earth_pct)}</text>`;
      });
    $("#tradeoff-chart").innerHTML = svgWrap(
      W,
      H,
      inner,
      "Dumbbell chart of solar availability and Earth visibility for six lunar sites"
    );
  }

  function renderSensitivity() {
    const W = 600;
    const H = 320;
    const m = { l: 118, r: 104, t: 28, b: 34 };
    const plotW = W - m.l - m.r;
    const plotH = H - m.t - m.b;
    const rowH = plotH / D.sites.length;
    const lo = 35;
    const hi = 92;
    const x = (v) => m.l + ((v - lo) / (hi - lo)) * plotW;
    let inner = "";
    [40, 50, 60, 70, 80, 90].forEach((v) => {
      inner += `<line x1="${x(v)}" y1="${m.t - 4}" x2="${x(v)}" y2="${m.t + plotH}" stroke="rgba(148,178,224,.12)" stroke-width="1"/>`;
      inner += `<text x="${x(v)}" y="${m.t - 11}" text-anchor="middle" fill="#6f829f" font-size="10">${v}</text>`;
    });
    D.sites
      .slice()
      .sort((a, b) => a.rank - b.rank)
      .forEach((site, i) => {
        const yy = m.t + i * rowH + rowH / 2;
        const p10 = site.score_p10 == null ? site.score : site.score_p10;
        const p90 = site.score_p90 == null ? site.score : site.score_p90;
        const color = site.rank === 1 ? "#f2b84b" : "#79aaff";
        inner += `<line x1="${x(p10)}" y1="${yy}" x2="${x(p90)}" y2="${yy}" stroke="${color}" stroke-opacity=".32" stroke-width="7" stroke-linecap="round"/>`;
        inner += `<circle cx="${x(site.score)}" cy="${yy}" r="6" fill="${color}" stroke="#0b1321" stroke-width="2"><title>${esc(site.name)}: baseline ${num(site.score, 1)}, p10-p90 ${num(p10, 1)}-${num(p90, 1)}</title></circle>`;
        inner += `<text x="${m.l - 12}" y="${yy + 4}" text-anchor="end" fill="${site.rank === 1 ? "#f2b84b" : "#e9eefb"}" font-size="12" font-weight="600">${esc(site.short_name)}</text>`;
        inner += `<text x="${W - 8}" y="${yy + 4}" text-anchor="end" fill="${site.rank === 1 ? "#f2b84b" : "#8fa1bd"}" font-size="10">${prob(site.top1)} top-1</text>`;
      });
    inner += `<text x="${m.l}" y="${H - 8}" fill="#6f829f" font-size="10">p10–p90 score range; dot = baseline mean</text>`;
    $("#sensitivity-chart").innerHTML = svgWrap(
      W,
      H,
      inner,
      "Sensitivity chart of baseline score ranges and top-1 probabilities"
    );
  }

  /* -------------------------------------------------------------- matrix */
  function scoreColor(score) {
    const s = Math.max(0, Math.min(100, score));
    const hue = s * 1.2;
    const light = 16 + s * 0.11;
    return `hsl(${hue.toFixed(0)} 58% ${light.toFixed(0)}%)`;
  }

  function renderMatrix() {
    const header = `<thead><tr><th>Site</th>${D.criteria
      .map(
        (c) =>
          `<th ${tip(c.label, `${c.description} ${c.caveat}`)}>${esc(c.short_label)}</th>`
      )
      .join("")}<th>Score</th></tr></thead>`;
    const body = D.sites
      .map(
        (site) => `<tr>
          <th>#${String(site.rank).padStart(2, "0")} ${esc(site.short_name)}<span>${esc(site.region)}</span></th>
          ${D.criteria
            .map((c) => {
              const cell = site.criteria[c.id];
              return `<td tabindex="0" style="background:${scoreColor(cell.score)}"
                ${tip(`${c.label} · ${site.short_name}`, `${cell.raw} ${cell.unit}. ${cell.rationale} Tier ${cell.tier}.`)}>
                <span class="cell-score">${num(cell.score, 0)}</span>
                <span class="cell-tier">${esc(cell.tier)}</span>
              </td>`;
            })
            .join("")}
          <td class="overall" tabindex="0" ${tip(`Weighted score · ${site.short_name}`, `Baseline weighted total ${num(site.score, 1)} / 100. Top-1 probability ${prob(site.top1)}.`)}>
            <span class="cell-score">${num(site.score, 1)}</span>
            <span class="cell-tier">baseline</span>
          </td>
        </tr>`
      )
      .join("");
    $("#score-matrix").innerHTML = header + `<tbody>${body}</tbody>`;
    $("#matrix-legend").innerHTML = `
      <span class="legend-swatch"><i style="background:linear-gradient(90deg,${scoreColor(0)},${scoreColor(50)},${scoreColor(100)})"></i> 0 → 100 criterion score</span>
      <span><span class="${tierClass("A")}">A</span> ground truth</span>
      <span><span class="${tierClass("B")}">B</span> measured / documented</span>
      <span><span class="${tierClass("C")}">C</span> analyst judgment</span>
      <span>Hover or focus a cell for raw values and rationale.</span>`;
  }

  /* ------------------------------------------------------------- profiles */
  function renderProfileCards() {
    $("#profile-grid").innerHTML = Object.values(D.profiles)
      .map((profile) => {
        const top = profile.ranking[0];
        const site = byId[top.site_id];
        const top3 = profile.ranking.slice(0, 3);
        return `<article class="profile-card ${profile.id === activeProfile ? "active" : ""}" data-profile="${esc(profile.id)}">
          <span class="p-label">${profile.id === "baseline" ? "Baseline" : "Profile"}</span>
          <h3>${esc(profile.label)}</h3>
          <div class="p-winner">${esc(site.short_name)}</div>
          <div class="p-score"><strong>${num(top.score, 1)}</strong><span>/ 100</span></div>
          <p>${esc(profile.description)}</p>
          <ul class="p-list">${top3
            .map(
              (row) =>
                `<li><span>#${row.rank} ${esc(siteName(row.site_id))}</span><strong>${num(row.score, 1)}</strong></li>`
            )
            .join("")}</ul>
        </article>`;
      })
      .join("");
    document.querySelectorAll(".profile-card").forEach((card) => {
      card.addEventListener("click", () =>
        selectProfile(card.dataset.profile, true)
      );
    });
  }

  /* --------------------------------------------------------------- sites */
  function renderSiteCards() {
    $("#site-cards").innerHTML = D.sites
      .map((site) => {
        const pin = site.pinpoint;
        return `<article class="site-card">
          <div class="site-media">
            <img src="${esc(site.hillshade)}" alt="Hillshade terrain around ${esc(site.name)}" decoding="async">
            <div class="media-top">
              <span class="rank-pill ${site.rank === 1 ? "first" : ""}">Rank ${String(site.rank).padStart(2, "0")} · ${esc(site.site_type.replace(/_/g, " "))}</span>
              <div class="media-score"><strong>${num(site.score, 1)}</strong><span>score / 100</span></div>
            </div>
            <div class="media-bottom">
              <h3>${esc(site.name)}</h3>
              <p>${coord(site.lat, site.lon)} · ${esc(site.region)}</p>
            </div>
          </div>
          <div class="site-body">
            <div class="site-metrics">
              <div class="site-metric"><span>Solar</span><strong>${pct(site.solar_pct)}</strong></div>
              <div class="site-metric"><span>Earth &gt;5°</span><strong>${pct(site.earth_pct)}</strong></div>
              <div class="site-metric"><span>Slope p90</span><strong>${num(site.slope_p90_deg, 1)}°</strong></div>
              <div class="site-metric"><span>PSR edge</span><strong>${num(site.psr_edge_km, 1)} km</strong></div>
            </div>
            <div class="site-metrics" style="margin-top:8px">
              <div class="site-metric"><span>Pinpoint p90</span><strong>${num(pin.slope_p90_deg, 1)}°</strong></div>
              <div class="site-metric"><span>Pad offset</span><strong>${num(pin.offset_km * 1000, 0)} m</strong></div>
              <div class="site-metric"><span>Open sky &gt;5°</span><strong>${pct((pin.open_sky_frac_5deg || 0) * 100, 0)}</strong></div>
              <div class="site-metric"><span>Relay</span><strong>${site.relay_required === "yes" ? "Required" : "No"}</strong></div>
            </div>
            <details class="site-details">
              <summary>Terrain, DEM &amp; pinpoint details</summary>
              <div class="detail-grid">
                <div><span>Elevation</span><strong>${num(site.elevation_m, 0)} m</strong></div>
                <div><span>DEM</span><strong>${esc(site.dem_label)}</strong></div>
                <div><span>Resolution</span><strong>${num(site.dem_res_m, 0)} m/px</strong></div>
                <div><span>Roughness</span><strong>${num(site.roughness_m, 1)} m</strong></div>
                <div><span>Horizon max</span><strong>${num(site.horizon_max_deg, 1)}°</strong></div>
                <div><span>Local relief</span><strong>${num(site.relief_m, 0)} m</strong></div>
                <div><span>Pinpoint</span><strong>${coord(pin.lat, pin.lon)}</strong></div>
                <div><span>Pad elevation</span><strong>${num(pin.elevation_m, 0)} m</strong></div>
                <div><span>Longest dark</span><strong>${hours(site.solar_hours_dark)}</strong></div>
                <div><span>Comms outage</span><strong>${hours(site.earth_outage_h)}</strong></div>
              </div>
              <p class="site-note"><strong>Science:</strong> ${esc(site.science_focus)}</p>
              <p class="site-note"><strong>Heritage:</strong> ${esc(site.heritage)}</p>
            </details>
          </div>
        </article>`;
      })
      .join("");
  }

  /* ---------------------------------------------------------------- data */
  function renderData() {
    const gaps = D.gaps;
    const priority = gaps.by_priority || {};
    const datasets = Object.entries(gaps.by_dataset || {}).sort(
      (a, b) => b[1] - a[1]
    );
    const max = Math.max(...datasets.map(([, count]) => count), 1);
    $("#gap-summary").innerHTML = `
      <div class="ledger-top">
        <div><strong>${D.meta.gap_count}</strong><span>total gaps</span></div>
        <div><strong>${priority.P0 || 0}</strong><span>P0 blocking</span></div>
        <div><strong>${priority.P1 || 0}</strong><span>P1 high</span></div>
      </div>
      ${datasets
        .map(
          ([name, count]) =>
            `<div class="ledger-row"><span class="l-name">${esc(name)}</span><span class="l-count">${count}</span><span class="ledger-bar"><i style="width:${(count / max) * 100}%"></i></span></div>`
        )
        .join("")}
      <p class="small" style="margin-top:14px">Every gap has a placeholder schema in
      <code>placeholders/</code> and an AOI + acceptance test in
      <code>data/processed/data_gaps.csv</code>.</p>`;

    $("#gap-list").innerHTML = gaps.p0
      .map(
        (gap) => `<div class="gap-item">
          <div class="g-head"><span class="g-site">${esc(siteName(gap.site_id))}</span>
          <span class="g-dataset">${esc(gap.dataset)}</span></div>
          <p>${esc(gap.why)}</p>
          <p><strong>Request:</strong> ${esc(gap.request_spec)}</p>
          <div class="g-meta">AOI ${esc(gap.aoi)}<br>${esc(gap.request_from)}</div>
        </div>`
      )
      .join("");

    $("#photo-strip").innerHTML = D.sites
      .map(
        (site) => `<article class="photo-card">
          <img src="${esc(site.photo)}" alt="${esc(site.photo_caption)}" decoding="async">
          <div class="photo-copy">
            <span class="photo-site">${esc(site.short_name)}</span>
            <h4>${esc(site.photo_caption)}</h4>
            <p>NASA Image Library · ${esc(site.photo_nasa_id || "asset")}</p>
          </div>
        </article>`
      )
      .join("");
  }

  /* -------------------------------------------------------------- method */
  function renderMethod() {
    const weights = D.profiles[D.baseline_profile].weights;
    const sorted = Object.entries(weights).sort((a, b) => b[1] - a[1]);
    const max = sorted[0][1];
    $("#weights-chart").innerHTML = sorted
      .map(([cid, weight]) => {
        const criterion = D.criteria.find((c) => c.id === cid);
        return `<div class="weight-row"><span>${esc(criterion ? criterion.short_label : cid)}</span>
          <span class="w-bar"><i style="width:${(weight / max) * 100}%"></i></span>
          <b>${Math.round(weight * 100)}%</b></div>`;
      })
      .join("");

    $("#caveat-list").innerHTML = D.recommendation.caveats
      .map((caveat) => `<li>${esc(caveat)}</li>`)
      .join("");

    $("#source-count").textContent =
      `${D.sources.length} sources · accessed 2026-11-14 · the NASA API key lives only in the gitignored .env`;

    $("#source-table").innerHTML = `
      <thead><tr><th>ID</th><th>Source</th><th>Notes</th><th>Status</th></tr></thead>
      <tbody>${D.sources
        .map(
          (source) => `<tr>
            <td>${esc(source.id)}</td>
            <td><a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.name)}</a><br><span style="color:var(--muted-2);font-size:.6rem">${esc(source.credit)}</span></td>
            <td>${esc(source.notes)}</td>
            <td>${esc(source.status)}</td>
          </tr>`
        )
        .join("")}</tbody>`;

    const meta = D.meta;
    $("#footer-meta").textContent =
      `Generated ${meta.generated_at} · window ${meta.window_start.slice(0, 10)} to ${meta.window_end.slice(0, 10)} · ` +
      `${meta.ephemeris_rows.toLocaleString()} samples · not a certified landing site.`;
  }

  /* -------------------------------------------------------------- tooltip */
  function setupTooltip() {
    const tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    tooltip.setAttribute("role", "tooltip");
    document.body.appendChild(tooltip);

    const move = (event) => {
      const pad = 14;
      const x =
        event.clientX + pad + tooltip.offsetWidth > window.innerWidth
          ? event.clientX - tooltip.offsetWidth - pad
          : event.clientX + pad;
      const y =
        event.clientY + pad + tooltip.offsetHeight > window.innerHeight
          ? event.clientY - tooltip.offsetHeight - pad
          : event.clientY + pad;
      tooltip.style.left = `${Math.max(8, x)}px`;
      tooltip.style.top = `${Math.max(8, y)}px`;
    };

    const show = (target, event) => {
      const title = target.getAttribute("data-tip-title");
      const body = target.getAttribute("data-tip-body");
      if (!title && !body) return;
      tooltip.innerHTML = `<span class="tt-head">${esc(title || "")}</span>${esc(body || "")}`;
      tooltip.classList.add("visible");
      if (event && event.clientX != null) move(event);
    };

    const hide = () => tooltip.classList.remove("visible");

    document.addEventListener("mouseover", (event) => {
      const target = event.target.closest("[data-tip-title]");
      if (target) show(target, event);
    });
    document.addEventListener("mousemove", (event) => {
      if (tooltip.classList.contains("visible")) move(event);
    });
    document.addEventListener("mouseout", (event) => {
      if (event.target.closest("[data-tip-title]")) hide();
    });
    document.addEventListener("focusin", (event) => {
      const target = event.target.closest("[data-tip-title]");
      if (!target) return;
      show(target, null);
      const rect = target.getBoundingClientRect();
      tooltip.style.left = `${Math.min(window.innerWidth - 330, Math.max(8, rect.left))}px`;
      tooltip.style.top = `${Math.min(window.innerHeight - 80, rect.bottom + 8)}px`;
    });
    document.addEventListener("focusout", (event) => {
      if (event.target.closest("[data-tip-title]")) hide();
    });
    window.addEventListener("scroll", hide, { passive: true });
  }

  /* ---------------------------------------------------------------- boot */
  renderHero();
  renderVerdict();
  renderProfileTabs();
  renderRanking();
  renderTradeoff();
  renderSensitivity();
  renderMatrix();
  renderProfileCards();
  renderSiteCards();
  renderData();
  renderMethod();
  setupTooltip();
})();
