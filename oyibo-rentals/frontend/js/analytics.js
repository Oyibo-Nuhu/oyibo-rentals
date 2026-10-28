// Control room → Analytics. Grown from the original Streamlit rental_dashboard.py.
// Everything here is filterable from one row of controls, and most charts double as filters:
// click a class bar, a rental-type bar or a map bubble to drill in.
import { api, naira, session } from "./api.js";
import { $, $$, esc, fmtDate, state } from "./app.js";
import { makeMap } from "./trips.js";

// ---------- colours: one fixed hue per vehicle class (validated for colour-blind separation) ----------
const cssVar = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
export const C = {
  get brake() { return cssVar("--brake", "#FF2E63"); },
  get xenon() { return cssVar("--xenon", "#B79CFF"); },
  get hazard() { return cssVar("--hazard", "#FF5A1F"); },
  get go() { return cssVar("--go", "#45E3A0"); },
};
const TIER_KEYS = ["luxury", "executive", "economy", "commercial", "truck", "bike", "tricycle"];
const tierColor = (t) => cssVar(`--t-${t}`, "#A8939F");
const tierLabel = (t) => state.meta.tiers.find((x) => x.key === t)?.label || t;

function theme() {
  const css = getComputedStyle(document.documentElement);
  return { text: css.getPropertyValue("--text").trim(), muted: css.getPropertyValue("--muted").trim(),
    line: css.getPropertyValue("--line").trim(), surface: css.getPropertyValue("--surface").trim() };
}

export function plot(id, data, layout = {}, config = {}) {
  const el = document.getElementById(id);
  if (!el || !window.Plotly) return null;
  const t = theme();
  Plotly.react(el, data, {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Instrument Sans, sans-serif", color: t.muted, size: 12 },
    margin: { t: 10, r: 12, b: 40, l: 60 }, bargap: 0.25,
    hoverlabel: { font: { family: "Instrument Sans", color: t.text }, bgcolor: t.surface, bordercolor: t.line },
    legend: { orientation: "h", y: -0.22, font: { color: t.text } }, ...layout,
    xaxis: { gridcolor: t.line, zerolinecolor: t.line, linecolor: t.line, ...(layout.xaxis || {}) },
    yaxis: { gridcolor: t.line, zerolinecolor: t.line, linecolor: t.line, ...(layout.yaxis || {}) },
  }, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"], ...config });
  return el;
}

const box = (id, title, cap, cls = "") =>
  `<div class="chart-box ${cls}"><h3>${title}</h3><p class="cap">${cap}</p><div class="chart" id="${id}"></div></div>`;

// ---------- the original dashboard's four charts (also used for CSV uploads) ----------
export function coreCharts(prefix) {
  return `
    ${box(prefix + "monthly", "Monthly rental charges", "Sum of final charges by rental start month. Hover for rental counts.")}
    ${box(prefix + "type", "Charges by vehicle class", "Total charges per class. Hover for rentals and average charge.")}
    ${box(prefix + "status", "Rental status mix", "Share of unique rentals in each status.")}
    ${box(prefix + "scatter", "Distance and duration", "One point per rental. High and left: short trips that covered a lot of ground.")}`;
}

export function drawCore(prefix, rep) {
  plot(prefix + "monthly", [{ x: rep.monthly.map((m) => m.month), y: rep.monthly.map((m) => m.revenue), customdata: rep.monthly.map((m) => m.rentals),
    type: "scatter", mode: "lines+markers", line: { width: 2, color: C.brake }, marker: { size: 8, color: C.brake },
    hovertemplate: "<b>₦%{y:,.0f}</b><br>%{x} · %{customdata} rentals<extra></extra>" }],
    { yaxis: { tickprefix: "₦", rangemode: "tozero" }, hovermode: "x unified" });
  plot(prefix + "type", [{ x: rep.by_type.map((t) => t.revenue), y: rep.by_type.map((t) => t.vehicle_type), orientation: "h", type: "bar",
    customdata: rep.by_type.map((t) => [t.rentals, t.average_charge]), marker: { color: C.brake },
    hovertemplate: "<b>₦%{x:,.0f}</b><br>%{y}<br>%{customdata[0]} rentals · avg ₦%{customdata[1]:,.0f}<extra></extra>" }],
    { margin: { t: 10, r: 12, b: 40, l: 170 }, xaxis: { tickprefix: "₦" } });
  const statusColors = { "Returned": C.xenon, "Currently Rented": C.go, "Reserved": C.brake };
  plot(prefix + "status", [{ labels: rep.by_status.map((s) => s.status), values: rep.by_status.map((s) => s.rentals), type: "pie", hole: 0.6,
    marker: { colors: rep.by_status.map((s) => statusColors[s.status] || "#A8939F"), line: { color: theme().surface, width: 2 } },
    hovertemplate: "<b>%{value} rentals</b><br>%{label} · %{percent}<extra></extra>" }], { margin: { t: 10, r: 10, b: 10, l: 10 } });
  const types = [...new Set(rep.scatter.map((r) => r.vehicle_type))];
  const keyFor = (label) => state.meta.tiers.find((t) => t.label === label)?.key;
  plot(prefix + "scatter", types.map((tp) => {
    const rows = rep.scatter.filter((r) => r.vehicle_type === tp);
    return { name: tp, x: rows.map((r) => r.rental_days), y: rows.map((r) => r.mileage_km), mode: "markers", type: "scatter",
      marker: { size: 8, opacity: 0.75, color: keyFor(tp) ? tierColor(keyFor(tp)) : undefined, line: { color: theme().surface, width: 1 } },
      customdata: rows.map((r) => [r.rental_id, r.final_cost, r.speeding_events]),
      hovertemplate: "<b>%{customdata[0]}</b><br>%{x:.2f} days · %{y:,.0f} km<br>₦%{customdata[1]:,.0f} · %{customdata[2]} speed alerts<extra></extra>" };
  }), { xaxis: { title: "Rental days", type: "log" }, yaxis: { title: "Distance (km)" } });
}

// ---------- small helpers ----------
const ICONS = {
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  crown: '<path d="M3 8l4 4 5-7 5 7 4-4-2 11H5z"/>',
  gauge: '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  parking: '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M10 17V8h3a3 3 0 0 1 0 6h-3"/>',
  leaf: '<path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15"/><path d="M5 19l7-7"/>',
};
const icon = (k) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k] || ICONS.trend}</svg>`;

function spark(values, color) {
  if (!values?.length || values.length < 2) return "";
  const w = 120, h = 30, max = Math.max(...values, 1), min = Math.min(...values, 0);
  const pts = values.map((v, i) => [i * (w / (values.length - 1)), h - 2 - ((v - min) / (max - min || 1)) * (h - 6)]);
  const line = pts.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <polygon points="0,${h} ${line} ${w},${h}" fill="${color}" opacity=".14"/><polyline points="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>`;
}

const shown = new Map(); // last displayed value per counter, so numbers roll from old to new on filter changes
function countUp(el, to, fmt) {
  const from = shown.get(el.id) ?? 0;
  shown.set(el.id, to);
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(to); return; }
  const t0 = performance.now(), dur = 900;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const compact = (n) => n >= 1e9 ? `₦${(n / 1e9).toFixed(2)}B` : n >= 1e6 ? `₦${(n / 1e6).toFixed(1)}M` : naira(n);

// ---------- filters (kept in the URL so a view can be shared) ----------
const RANGES = [["30", "30 days"], ["90", "90 days"], ["365", "1 year"], ["all", "All time"]];

function readFilters() {
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  return { range: q.get("range") || "all", start: q.get("start") || "", end: q.get("end") || "",
    tiers: (q.get("tiers") || "").split(",").filter(Boolean), modes: (q.get("modes") || "").split(",").filter(Boolean), zone: q.get("zone") || "" };
}

function writeFilters(f) {
  const q = new URLSearchParams();
  if (f.range !== "all") q.set("range", f.range);
  if (f.range === "custom") { if (f.start) q.set("start", f.start); if (f.end) q.set("end", f.end); }
  if (f.tiers.length) q.set("tiers", f.tiers.join(","));
  if (f.modes.length) q.set("modes", f.modes.join(","));
  if (f.zone) q.set("zone", f.zone);
  history.replaceState(null, "", `#/admin/analytics${q.toString() ? "?" + q : ""}`);
}

function apiQuery(f) {
  const q = new URLSearchParams();
  if (f.range === "custom") { if (f.start) q.set("start", f.start); if (f.end) q.set("end", f.end); }
  else if (f.range !== "all") {
    const d = new Date(Date.now() - Number(f.range) * 864e5);
    q.set("start", d.toISOString().slice(0, 10));
  }
  if (f.tiers.length) q.set("tiers", f.tiers.join(","));
  if (f.modes.length) q.set("modes", f.modes.join(","));
  if (f.zone) q.set("zone", f.zone);
  return q.toString();
}

// ---------- the tab ----------
export async function analyticsTab(body) {
  const f = readFilters();
  let rep = null, map = null, mapLayer = null, mapMetric = "rentals", raceDone = false, observer = null, loading = 0;

  body.innerHTML = `
    <div class="filterbar" role="region" aria-label="Analytics filters">
      <div class="seg" id="f-range" role="group" aria-label="Date range">
        ${RANGES.map(([k, l]) => `<button type="button" data-range="${k}">${l}</button>`).join("")}
        <button type="button" data-range="custom">Custom</button>
      </div>
      <span class="custom-dates" id="f-custom" hidden>
        <input type="date" id="f-start" aria-label="From date"> <span class="muted">to</span> <input type="date" id="f-end" aria-label="To date">
      </span>
      <div class="chips" id="f-tiers" role="group" aria-label="Vehicle classes"></div>
      <select id="f-mode" aria-label="Rental type"><option value="">All rental types</option></select>
      <select id="f-zone" aria-label="Pickup point"><option value="">All pickup points</option></select>
      <button type="button" class="btn btn-sm btn-ghost" id="f-reset">Reset</button>
      <a class="btn btn-sm btn-ghost" href="#" id="export">Export CSV</a>
    </div>
    <div id="an-body" class="an-body"><div class="skeleton"></div></div>
    <div class="panel" style="margin-top:24px">
      <h2>Analyze a CSV</h2>
      <p class="muted">Upload rental records from another system. Required columns: rental_date, vehicle_type, rental_days, final_cost. Optional: rental_id, vehicle_id, mileage_km, speeding_events, status.</p>
      <input type="file" id="csv" accept=".csv" style="max-width:420px">
      <div id="csv-out" style="margin-top:20px"></div>
    </div>`;

  const out = $("#an-body");

  function paintControls() {
    $$("#f-range button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.range === f.range));
    $("#f-custom").hidden = f.range !== "custom";
    if (!rep?.options) return;
    const o = rep.options;
    $("#f-start").min = $("#f-end").min = o.min_date; $("#f-start").max = $("#f-end").max = o.max_date;
    $("#f-start").value = f.start || o.min_date; $("#f-end").value = f.end || o.max_date;
    $("#f-tiers").innerHTML = o.tiers.map((t) => `<button type="button" class="chip" data-tier="${t.key}" aria-pressed="${f.tiers.includes(t.key)}">
      <i style="background:${tierColor(t.key)}"></i>${esc(t.label.replace(/ \(.*\)/, ""))}</button>`).join("");
    $("#f-mode").innerHTML = `<option value="">All rental types</option>` + o.modes.map((m) => `<option value="${m.key}" ${f.modes[0] === m.key ? "selected" : ""}>${esc(m.label)}</option>`).join("");
    $("#f-zone").innerHTML = `<option value="">All pickup points</option>` + o.zones.map((z) => `<option value="${z.key}" ${f.zone === z.key ? "selected" : ""}>${esc(z.name)}</option>`).join("");
    $$("#f-tiers .chip").forEach((c) => c.onclick = () => {
      const k = c.dataset.tier;
      f.tiers = f.tiers.includes(k) ? f.tiers.filter((x) => x !== k) : [...f.tiers, k];
      refresh();
    });
  }

  $$("#f-range button").forEach((b) => b.onclick = () => { f.range = b.dataset.range; refresh(); });
  $("#f-start").onchange = $("#f-end").onchange = () => { f.start = $("#f-start").value; f.end = $("#f-end").value; refresh(); };
  $("#f-mode").onchange = (e) => { f.modes = e.target.value ? [e.target.value] : []; refresh(); };
  $("#f-zone").onchange = (e) => { f.zone = e.target.value; refresh(); };
  $("#f-reset").onclick = () => { Object.assign(f, { range: "all", start: "", end: "", tiers: [], modes: [], zone: "" }); refresh(); };

  async function refresh() {
    writeFilters(f);
    paintControls();
    const my = ++loading;
    out.classList.add("loading");
    let next;
    try { next = await api(`/api/admin/analytics?${apiQuery(f)}`); }
    catch (e) { out.classList.remove("loading"); out.innerHTML = `<p style="color:var(--alert)">${esc(e.message)}</p>`; return; }
    if (my !== loading || !body.isConnected) return;
    rep = next;
    out.classList.remove("loading");
    paintControls();
    if (rep.empty) { out.innerHTML = `<div class="empty"><p>No rentals yet. Analytics appear once bookings come in.</p></div>`; return; }
    if (rep.no_match) { out.innerHTML = `<div class="empty"><h3>Nothing matches these filters</h3><p>Widen the date range or clear a filter.</p><button class="btn btn-primary" id="nm-reset">Reset filters</button></div>`;
      $("#nm-reset").onclick = () => $("#f-reset").click(); return; }
    await draw();
  }

  async function draw() {
    const k = rep.kpis, fc = rep.forecast;
    if (!$("#an-grid")) {
      out.innerHTML = `
        <div class="insights" id="insights" aria-label="Insights"></div>
        <div class="kpis kpis-live" id="an-kpis"></div>
        <div class="charts" id="an-grid">
          <div class="chart-box wide podium-box"><h3>Fleet podium</h3><p class="cap">Top earners in this view. Revenue is the sum of final charges.</p><div id="podium"></div></div>
          <div class="chart-box wide"><div class="box-head"><div><h3>The revenue race</h3><p class="cap">Cumulative revenue by vehicle class, month by month. Press play, or drag the slider.</p></div></div><div class="chart chart-tall" id="c-race"></div></div>
          ${box("c-tier", "Revenue by class", "Click a bar to focus the whole dashboard on that class. Click again to clear.")}
          ${box("c-mode", "Revenue by rental type", "Go-anywhere rentals earn more per booking; route trips drive volume. Click to filter.")}
          <div class="chart-box wide"><div class="box-head"><div><h3>Where trips start</h3><p class="cap">Route pickups across Lagos. Bubble size shows the selected measure. Click a bubble to filter by that pickup point.</p></div>
            <div class="seg seg-sm" id="map-metric" role="group" aria-label="Map measure"><button data-m="rentals" aria-pressed="true">Trips</button><button data-m="revenue" aria-pressed="false">Revenue</button><button data-m="speeding" aria-pressed="false">Speeding</button></div></div>
            <div class="an-map" id="an-map"></div></div>
          <div class="chart-box wide"><h3>Every day, at a glance</h3><p class="cap">Daily revenue for up to a year. Each square is a day; darker means more revenue. Hover for the numbers.</p><div class="calendar" id="calendar"></div></div>
          <div class="chart-box wide sim"><h3>Pricing what-if</h3>
            <p class="cap">Move the sliders to see what a price change could do to the last 30 days in this view. This uses an assumed price elasticity, not a fitted model: treat it as a thinking tool.</p>
            <div class="sim-grid">
              <div>
                <label for="sim-price">Price change <b id="sim-price-v">+0%</b></label><input type="range" id="sim-price" min="-30" max="30" step="1" value="0">
                <label for="sim-el" style="margin-top:14px">How sensitive customers are <b id="sim-el-v">−1.1</b></label><input type="range" id="sim-el" min="-25" max="-3" step="1" value="-11">
                <div class="hint">−0.3 = they barely notice the price · −2.5 = they leave fast. Most rental markets sit near −1.</div>
                <label for="sim-tier" style="margin-top:14px">Apply to</label><select id="sim-tier"></select>
              </div>
              <div class="sim-out">
                <div><span>Revenue</span><b id="sim-rev">–</b><small id="sim-rev-d"></small></div>
                <div><span>Rentals</span><b id="sim-n">–</b><small id="sim-n-d"></small></div>
                <p class="sim-verdict" id="sim-verdict" aria-live="polite"></p>
              </div>
              <div class="chart chart-short" id="c-sim"></div>
            </div></div>
          ${box("c-monthly", "Monthly rental charges", "Sum of final charges by rental start month. Hover for rental counts.")}
          ${box("c-forecast", "Demand forecast", "")}
          ${box("c-heat", "When people rent", "Bookings by weekday and start hour. Darker cells are busier.", "wide")}
          ${box("c-speed", "Speeding by hour", "Alerts over the speed limit by trip start hour.")}
          ${box("c-loss", "Insurance loss ratio", "Claims paid ÷ premiums collected. Above 1.0 means the plan loses money.")}
          ${box("c-seg", "Customer segments", "K-means on recency, trip count and spend. Each point is a customer. Click a legend item to hide a segment.", "wide")}
          <div class="chart-box"><h3>Segment profiles</h3><p class="cap">Average values per segment. Target "at risk" customers with a win-back offer.</p><div class="table-wrap"><table id="seg-table"></table></div></div>
          <div class="chart-box"><h3>Driver risk</h3><p class="cap">0–100 from speeding per 100 km (40%), top speed (25%), claims (20%) and late returns (15%). 2+ trips.</p><div class="table-wrap"><table id="risk-table"></table></div></div>
          ${box("c-util", "Fleet utilization, last 30 days", "Share of hours each vehicle was booked. Low bars are candidates for repricing or relocation.", "wide")}
          ${box("c-status", "Rental status mix", "Share of unique rentals in each status.")}
          ${box("c-scatter", "Distance and duration", "One point per rental, coloured by class.")}
        </div>
        <p class="muted an-foot" id="an-foot"></p>`;
      $$("#map-metric button").forEach((b) => b.onclick = () => { mapMetric = b.dataset.m; $$("#map-metric button").forEach((x) => x.setAttribute("aria-pressed", x === b)); drawMap(); });
      ["sim-price", "sim-el", "sim-tier"].forEach((id) => $("#" + id).addEventListener("input", drawSim));
    }

    // insights
    $("#insights").innerHTML = rep.insights.map((i, n) => `<article class="insight" style="--d:${n * 70}ms">${icon(i.icon)}<div><b>${esc(i.title)}</b><span>${esc(i.detail)}</span></div></article>`).join("");

    // KPIs
    const growth = k.revenue_growth == null ? "" : `<small class="${k.revenue_growth >= 0 ? "up" : "down"}">${k.revenue_growth >= 0 ? "▲" : "▼"} ${Math.abs(k.revenue_growth * 100).toFixed(1)}% vs previous 30 days</small>`;
    $("#an-kpis").innerHTML = `
      <div><span title="Sum of final charges. Recorded charges, not profit.">Total rental charges</span><b id="k-rev"></b>${spark(rep.spark.revenue, C.brake)}</div>
      <div><span>Last 30 days</span><b id="k-30"></b>${growth}</div>
      <div><span>Rentals</span><b id="k-n"></b><small>${k.customers} customers</small>${spark(rep.spark.rentals, C.xenon)}</div>
      <div><span>Average duration</span><b id="k-days"></b></div>
      <div><span>On the road now</span><b><i class="live-dot" aria-hidden="true"></i>${k.fleet_on_road} / ${k.fleet_size}</b></div>
      <div><span title="Recorded by tracking, over ${state.meta.speed_limit} km/h">Speeding events</span><b id="k-sp"></b>${spark(rep.spark.speeding, C.hazard)}</div>
      <div><span>Average rating</span><b>${k.average_rating ? k.average_rating.toFixed(2) + " ★" : "–"}</b></div>
      <div><span>Damage claim rate</span><b>${(rep.claims.claim_rate * 100).toFixed(1)}%</b><small>${rep.claims.open} open</small></div>`;
    countUp($("#k-rev"), k.total_revenue, (v) => naira(v));
    countUp($("#k-30"), k.revenue_30d, (v) => naira(v));
    countUp($("#k-n"), k.rental_count, (v) => Math.round(v).toLocaleString());
    countUp($("#k-days"), k.average_days, (v) => v.toFixed(1) + " days");
    countUp($("#k-sp"), k.speeding_events, (v) => Math.round(v).toLocaleString());

    drawPodium();
    drawCalendar();

    const wait = () => new Promise((r) => (window.Plotly ? r() : setTimeout(() => wait().then(r), 80)));
    await wait();
    if (!body.isConnected) return;

    // revenue by class (click to filter)
    const bt = [...rep.by_tier_key].sort((a, b) => a.revenue - b.revenue);
    const tierEl = plot("c-tier", [{ x: bt.map((t) => t.revenue), y: bt.map((t) => t.vehicle_type.replace(/ \(.*\)/, "")), orientation: "h", type: "bar",
      marker: { color: bt.map((t) => tierColor(t.tier)), opacity: bt.map((t) => (!f.tiers.length || f.tiers.includes(t.tier) ? 1 : 0.35)) },
      customdata: bt.map((t) => [t.rentals, t.average_charge, t.tier]),
      hovertemplate: "<b>₦%{x:,.0f}</b><br>%{y}<br>%{customdata[0]} rentals · avg ₦%{customdata[1]:,.0f}<br><i>Click to filter</i><extra></extra>" }],
      { margin: { t: 10, r: 12, b: 40, l: 110 }, xaxis: { tickprefix: "₦" } });
    tierEl?.removeAllListeners?.("plotly_click");
    tierEl?.on?.("plotly_click", (ev) => { const t = ev.points[0].customdata[2]; f.tiers = f.tiers.length === 1 && f.tiers[0] === t ? [] : [t]; refresh(); });

    const MODE_NAMES = Object.fromEntries(rep.options.modes.map((m) => [m.key, m.label]));
    const bm = rep.by_mode_key;
    const modeEl = plot("c-mode", [{ x: bm.map((m) => MODE_NAMES[m.mode]), y: bm.map((m) => m.revenue), type: "bar",
      marker: { color: C.xenon, opacity: bm.map((m) => (!f.modes.length || f.modes.includes(m.mode) ? 1 : 0.35)) },
      customdata: bm.map((m) => [m.rentals, m.avg_charge, m.mode]),
      hovertemplate: "<b>₦%{y:,.0f}</b><br>%{x}<br>%{customdata[0]} rentals · avg ₦%{customdata[1]:,.0f}<br><i>Click to filter</i><extra></extra>" }],
      { yaxis: { tickprefix: "₦" } });
    modeEl?.removeAllListeners?.("plotly_click");
    modeEl?.on?.("plotly_click", (ev) => { const m = ev.points[0].customdata[2]; f.modes = f.modes[0] === m ? [] : [m]; refresh(); });

    drawRace();
    drawMap();
    drawSimSetup();
    drawCore("c-", rep);

    if (fc.available) {
      $("#c-forecast").previousElementSibling.textContent = `Weekly rentals with an 8-week forecast and 95% band. Backtest error on the last 8 weeks: ±${fc.backtest_mae} rentals a week.`;
      const fx = fc.forecast.map((p) => p.week);
      plot("c-forecast", [
        { name: "Actual", x: fc.history.map((h) => h.week), y: fc.history.map((h) => h.rentals), type: "scatter", mode: "lines", line: { color: C.xenon, width: 2 },
          hovertemplate: "<b>%{y} rentals</b><br>week of %{x}<extra>Actual</extra>" },
        { name: "95% band", x: [...fx, ...fx.slice().reverse()], y: [...fc.forecast.map((p) => p.high), ...fc.forecast.map((p) => p.low).reverse()],
          fill: "toself", fillcolor: "rgba(255,46,99,.16)", line: { width: 0 }, mode: "lines", hoverinfo: "skip", type: "scatter" },
        { name: "Forecast", x: fx, y: fc.forecast.map((p) => p.rentals), type: "scatter", mode: "lines+markers", line: { color: C.brake, width: 2, dash: "dot" }, marker: { size: 8 },
          customdata: fc.forecast.map((p) => [p.low, p.high]), hovertemplate: "<b>%{y:.0f} rentals</b><br>range %{customdata[0]:.0f}–%{customdata[1]:.0f}<extra>Forecast</extra>" },
      ], { yaxis: { title: "Rentals per week", rangemode: "tozero" } });
    } else {
      $("#c-forecast").innerHTML = `<div class="empty"><p>${esc(fc.reason)} Widen the date range to see a forecast.</p></div>`;
    }

    const dark = !document.documentElement.dataset.theme;
    plot("c-heat", [{ z: rep.heatmap.values, x: rep.heatmap.hours.map((h) => `${h}:00`), y: rep.heatmap.days, type: "heatmap", xgap: 2, ygap: 2,
      colorscale: dark ? [[0, "#2A1A25"], [1, C.brake]] : [[0, "#FCE8EE"], [1, C.brake]], showscale: false,
      hovertemplate: "<b>%{z} rentals</b><br>%{y} %{x}<extra></extra>" }],
      { margin: { t: 10, r: 10, b: 40, l: 50 }, yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)" }, xaxis: { gridcolor: "rgba(0,0,0,0)" } });
    plot("c-speed", [{ x: rep.speeding_by_hour.map((s) => s.hour), y: rep.speeding_by_hour.map((s) => s.events), type: "bar", marker: { color: C.hazard },
      hovertemplate: "<b>%{y} alerts</b><br>trips starting %{x}:00<extra></extra>" }], { xaxis: { title: "Start hour", dtick: 3 } });
    plot("c-loss", [{ x: rep.claims.by_plan.map((p) => p.plan), y: rep.claims.by_plan.map((p) => p.loss_ratio), type: "bar",
      marker: { color: rep.claims.by_plan.map((p) => (p.loss_ratio > 1 ? C.hazard : C.go)) },
      text: rep.claims.by_plan.map((p) => (p.loss_ratio > 1 ? "Losing money" : "Profitable")), textposition: "outside",
      customdata: rep.claims.by_plan.map((p) => [p.claims, p.paid, p.premiums]),
      hovertemplate: "<b>Loss ratio %{y:.2f}</b><br>%{x}<br>%{customdata[0]} claims · paid ₦%{customdata[1]:,.0f}<br>premiums ₦%{customdata[2]:,.0f}<extra></extra>" }],
      { shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1, line: { color: theme().muted, dash: "dot", width: 1 } }], yaxis: { rangemode: "tozero" } });

    if (rep.segments.available) {
      const segColors = { "VIP regulars": C.brake, "Loyal riders": C.xenon, "Occasional riders": C.go, "At risk of churning": "#A8939F" };
      const segs = [...new Set(rep.segments.points.map((p) => p.segment))];
      plot("c-seg", segs.map((s) => {
        const pts = rep.segments.points.filter((p) => p.segment === s);
        return { name: s, x: pts.map((p) => p.frequency), y: pts.map((p) => p.spend), text: pts.map((p) => p.customer), customdata: pts.map((p) => p.recency_days),
          mode: "markers", type: "scatter", marker: { size: 10, opacity: 0.85, color: segColors[s], line: { color: theme().surface, width: 1.5 } },
          hovertemplate: "<b>%{text}</b><br>%{x} trips · ₦%{y:,.0f}<br>last trip %{customdata} days ago<extra>%{fullData.name}</extra>" };
      }), { xaxis: { title: "Trips", type: "log", tickvals: [1, 2, 3, 5, 10, 20, 30, 50, 100] },
        yaxis: { title: "Total spend", type: "log", tickvals: [1e4, 1e5, 1e6, 1e7, 1e8], ticktext: ["₦10k", "₦100k", "₦1M", "₦10M", "₦100M"] } });
      $("#seg-table").innerHTML = `<thead><tr><th>Segment</th><th>Customers</th><th>Trips</th><th>Spend</th><th>Days since</th></tr></thead><tbody>
        ${rep.segments.profiles.map((p) => `<tr><td><i class="dot" style="background:${segColors[p.segment]}"></i>${esc(p.segment)}</td><td>${p.customers}</td><td>${p.frequency}</td><td>${naira(p.spend)}</td><td>${p.recency_days}</td></tr>`).join("")}</tbody>`;
    } else {
      $("#c-seg").innerHTML = `<div class="empty"><p>Needs at least 8 customers in this view.</p></div>`;
      $("#seg-table").innerHTML = "";
    }
    $("#risk-table").innerHTML = `<thead><tr><th>Customer</th><th>Trips</th><th>Alerts /100km</th><th>Top speed</th><th>Claims</th><th>Score</th></tr></thead><tbody>
      ${rep.driver_risk.map((d) => `<tr><td>${esc(d.customer)}</td><td>${d.trips}</td><td>${d.speeding_per_100km}</td><td>${Math.round(d.max_speed)}</td><td>${d.claims}</td>
        <td><span class="riskbar band-${d.band}" style="--w:${Math.round(d.risk_score)}%"></span>${Math.round(d.risk_score)} ${d.band}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Not enough repeat customers in this view.</td></tr>`}</tbody>`;
    const util = rep.utilization.slice(0, 45);
    plot("c-util", [{ x: util.map((u) => u.vehicle), y: util.map((u) => u.utilization), type: "bar", marker: { color: util.map((u) => tierColor(u.tier)) },
      hovertemplate: "<b>%{y:.0%} booked</b><br>%{x}<extra></extra>" }], { yaxis: { tickformat: ".0%", rangemode: "tozero" }, margin: { t: 10, r: 10, b: 120, l: 50 } });

    const filt = [f.tiers.length && f.tiers.map(tierLabel).join(", "), f.modes.length && MODE_NAMES[f.modes[0]],
      f.zone && rep.options.zones.find((z) => z.key === f.zone)?.name].filter(Boolean);
    $("#an-foot").textContent = `Paid rentals only, including clearly flagged demo data until you switch it off. ${filt.length ? "Filtered to " + filt.join(" · ") + ". " : ""}Updated ${fmtDate(rep.generated_at, { timeStyle: "short" })}.`;
  }

  function drawPodium() {
    const p = rep.podium;
    if (!p.length) { $("#podium").innerHTML = ""; return; }
    const order = [p[1], p[0], p[2]].filter(Boolean);
    const place = (v) => p.indexOf(v) + 1;
    $("#podium").innerHTML = `<div class="podium">${order.map((v) => `
      <div class="step p${place(v)}" style="--c:${tierColor(v.tier)}">
        <div class="pod-photo">${v.photo ? `<img src="${esc(v.photo)}" alt="" loading="lazy">` : ""}<span class="medal">${place(v)}</span></div>
        <b>${esc(v.vehicle)}</b><span class="money" id="pod-${place(v)}"></span><small>${v.rentals} trips · ${v.km.toLocaleString()} km</small>
        <div class="block"></div>
      </div>`).join("")}</div>
      ${p.length > 3 ? `<ol class="runners" start="4">${p.slice(3).map((v) => `<li><i class="dot" style="background:${tierColor(v.tier)}"></i>${esc(v.vehicle)} <span class="muted">· ${naira(v.revenue)}</span></li>`).join("")}</ol>` : ""}`;
    order.forEach((v) => countUp($(`#pod-${place(v)}`), v.revenue, compact));
  }

  function drawCalendar() {
    const days = rep.calendar, el = $("#calendar");
    if (!days.length) { el.innerHTML = ""; return; }
    const max = Math.max(...days.map((d) => d.revenue), 1);
    const first = new Date(days[0].date + "T00:00:00");
    const offset = (first.getDay() + 6) % 7; // Monday first
    const cell = 13, gap = 3, weeks = Math.ceil((days.length + offset) / 7);
    const dark = !document.documentElement.dataset.theme;
    const shade = (v) => {
      if (!v) return dark ? "#2A1A25" : "#F0E4EA";
      const t = Math.sqrt(v / max);
      return `color-mix(in oklab, ${C.brake} ${Math.round(25 + t * 75)}%, ${dark ? "#2A1A25" : "#F0E4EA"})`;
    };
    let months = "", lastM = -1;
    const rects = days.map((d, i) => {
      const idx = i + offset, w = Math.floor(idx / 7), dow = idx % 7, dt = new Date(d.date + "T00:00:00");
      if (dt.getMonth() !== lastM && dow === 0) { lastM = dt.getMonth(); months += `<text x="${30 + w * (cell + gap)}" y="10">${dt.toLocaleString("en", { month: "short" })}</text>`; }
      return `<rect x="${30 + w * (cell + gap)}" y="${18 + dow * (cell + gap)}" width="${cell}" height="${cell}" rx="3" style="fill:${shade(d.revenue)}" data-i="${i}" tabindex="-1"/>`;
    }).join("");
    const W = 30 + weeks * (cell + gap), H = 18 + 7 * (cell + gap);
    el.innerHTML = `<div class="cal-scroll"><svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Daily revenue calendar">
      <g class="cal-labels">${months}<text x="0" y="${18 + cell}">Mon</text><text x="0" y="${18 + 2 * (cell + gap) + cell}">Wed</text><text x="0" y="${18 + 4 * (cell + gap) + cell}">Fri</text></g>${rects}</svg></div>
      <div class="cal-legend"><span>Less</span>${[0, .1, .3, .6, 1].map((t) => `<i style="background:${shade(t * max)}"></i>`).join("")}<span>More</span></div>
      <div class="viz-tip" id="cal-tip" hidden></div>`;
    const tip = $("#cal-tip");
    el.querySelector("svg").addEventListener("pointermove", (e) => {
      const r = e.target.closest("rect");
      if (!r) { tip.hidden = true; return; }
      const d = days[r.dataset.i];
      tip.replaceChildren();
      const b = document.createElement("b"); b.textContent = naira(d.revenue);
      const s = document.createElement("span"); s.textContent = `${new Date(d.date + "T00:00:00").toLocaleDateString("en-NG", { weekday: "short", day: "numeric", month: "short", year: "numeric" })} · ${d.rentals} rental${d.rentals === 1 ? "" : "s"}`;
      tip.append(b, s);
      const box = el.getBoundingClientRect();
      tip.hidden = false;
      tip.style.left = Math.min(box.width - 200, Math.max(0, e.clientX - box.left - 90)) + "px";
      tip.style.top = (e.clientY - box.top - 58) + "px";
    });
    el.querySelector("svg").addEventListener("pointerleave", () => (tip.hidden = true));
    const sc = el.querySelector(".cal-scroll"); sc.scrollLeft = sc.scrollWidth;
  }

  function drawRace() {
    const r = rep.race;
    if (!r.months.length) return;
    const frame = (i) => {
      const rows = r.tiers.map((t) => ({ key: t.key, label: t.label.replace(/ \(.*\)/, ""), v: r.values[t.key][i] })).sort((a, b) => a.v - b.v);
      return { x: rows.map((x) => x.v), y: rows.map((x) => x.label), marker: { color: rows.map((x) => tierColor(x.key)) },
        text: rows.map((x) => compact(x.v)) };
    };
    const max = Math.max(...r.tiers.map((t) => r.values[t.key].at(-1)));
    const startIdx = raceDone ? r.months.length - 1 : 0;
    const base = { type: "bar", orientation: "h", textposition: "outside", cliponaxis: false, hovertemplate: "<b>%{text}</b><br>%{y}<extra></extra>", ...frame(startIdx) };
    const el = plot("c-race", [base], {
      margin: { t: 10, r: 70, b: 90, l: 100 }, xaxis: { range: [0, max * 1.12], tickprefix: "₦", fixedrange: true }, yaxis: { fixedrange: true },
      annotations: [{ xref: "paper", yref: "paper", x: 0.98, y: 0.06, xanchor: "right", text: r.months[startIdx], showarrow: false,
        font: { family: "Michroma, sans-serif", size: innerWidth < 600 ? 16 : 30, color: theme().line.replace(/[\d.]+\)$/, "0.5)") } }],
      updatemenus: [{ type: "buttons", showactive: false, x: 0, y: -0.2, xanchor: "left", yanchor: "top", pad: { t: 0, r: 10 },
        bgcolor: C.brake, bordercolor: C.brake, font: { color: "#25000B" },
        buttons: [{ label: "▶ Play", method: "animate", args: [null, { frame: { duration: 650, redraw: true }, transition: { duration: 500, easing: "cubic-in-out" }, fromcurrent: false }] }] }],
      sliders: [{ active: startIdx, x: 0.12, len: 0.88, y: -0.12, pad: { t: 30 }, currentvalue: { visible: false }, font: { color: theme().muted },
        bgcolor: theme().line, activebgcolor: C.brake, bordercolor: "rgba(0,0,0,0)", ticklen: 0,
        steps: r.months.map((m) => ({ label: m.slice(2), method: "animate", args: [[m], { mode: "immediate", frame: { duration: 300, redraw: true }, transition: { duration: 250 } }] })) }],
    }, { displayModeBar: false });
    if (!el) return;
    Plotly.addFrames(el, r.months.map((m, i) => ({ name: m, data: [frame(i)], layout: { annotations: [{ ...el.layout.annotations[0], text: m }] } })));
    if (!raceDone && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      observer?.disconnect();
      observer = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          observer.disconnect(); raceDone = true;
          Plotly.animate(el, null, { frame: { duration: 650, redraw: true }, transition: { duration: 500, easing: "cubic-in-out" } });
        }
      }, { threshold: 0.5 });
      observer.observe(el);
    }
  }

  function drawMap() {
    const el = $("#an-map");
    if (!el || !window.L) return;
    if (!map) map = makeMap(el, { zoomControl: true, scrollWheelZoom: false });
    if (mapLayer) mapLayer.remove();
    const pts = rep.zone_map;
    if (!pts.length) return;
    const max = Math.max(...pts.map((p) => p[mapMetric]), 1);
    const color = mapMetric === "speeding" ? C.hazard : mapMetric === "revenue" ? C.brake : C.xenon;
    const fmt = { rentals: (v) => `${v.toLocaleString()} trips`, revenue: (v) => naira(v), speeding: (v) => `${v.toLocaleString()} speed alerts` }[mapMetric];
    mapLayer = L.layerGroup(pts.map((p) => {
      const sel = f.zone === p.key;
      const c = L.circleMarker([p.lat, p.lng], { radius: 6 + Math.sqrt(p[mapMetric] / max) * 26, color: sel ? theme().text : color, weight: sel ? 3 : 1.5,
        fillColor: color, fillOpacity: f.zone && !sel ? 0.18 : 0.45, className: "zone-bubble" });
      c.bindTooltip(`<b>${esc(p.name)}</b><br>${fmt(p[mapMetric])}<br><small>Click to ${sel ? "clear the filter" : "filter"}</small>`, { direction: "top" });
      c.on("click", () => { f.zone = sel ? "" : p.key; refresh(); });
      return c;
    })).addTo(map);
    map.fitBounds(L.latLngBounds(pts.map((p) => [p.lat, p.lng])).pad(0.15));
  }

  function drawSimSetup() {
    const sel = $("#sim-tier"), prev = sel.value;
    sel.innerHTML = `<option value="">Every class in this view</option>` + rep.simulator_base.map((b) => `<option value="${b.tier}">${esc(b.label)}</option>`).join("");
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
    drawSim();
  }

  function drawSim() {
    const p = Number($("#sim-price").value) / 100, e = Number($("#sim-el").value) / 10, only = $("#sim-tier").value;
    $("#sim-price-v").textContent = `${p >= 0 ? "+" : "−"}${Math.abs(Math.round(p * 100))}%`;
    $("#sim-el-v").textContent = `−${Math.abs(e).toFixed(1)}`;
    const rows = rep.simulator_base.map((b) => {
      const apply = !only || b.tier === only;
      const n = apply ? b.rentals * Math.pow(1 + p, e) : b.rentals;
      const rev = apply ? b.revenue * Math.pow(1 + p, 1 + e) : b.revenue;
      return { ...b, n, rev };
    });
    const r0 = rows.reduce((s, r) => s + r.revenue, 0), r1 = rows.reduce((s, r) => s + r.rev, 0);
    const n0 = rows.reduce((s, r) => s + r.rentals, 0), n1 = rows.reduce((s, r) => s + r.n, 0);
    const pct = (a, b) => (b ? (a - b) / b : 0);
    const dRev = pct(r1, r0), dN = pct(n1, n0);
    $("#sim-rev").textContent = compact(r1);
    $("#sim-n").textContent = Math.round(n1).toLocaleString();
    $("#sim-rev-d").textContent = `${dRev >= 0 ? "▲" : "▼"} ${Math.abs(dRev * 100).toFixed(1)}% (${dRev >= 0 ? "+" : "−"}${compact(Math.abs(r1 - r0))})`;
    $("#sim-rev-d").className = dRev >= 0 ? "up" : "down";
    $("#sim-n-d").textContent = `${dN >= 0 ? "▲" : "▼"} ${Math.abs(dN * 100).toFixed(1)}% trips`;
    $("#sim-n-d").className = dN >= 0 ? "up" : "down";
    const sens = Math.abs(e);
    $("#sim-verdict").textContent = p === 0 ? "Drag the price slider to try a change."
      : sens < 1 ? `Customers here are fairly loyal (${e.toFixed(1)}): a ${p > 0 ? "rise" : "cut"} ${p > 0 ? "adds" : "loses"} revenue even though trips ${p > 0 ? "dip" : "grow"}.`
      : sens > 1 ? `Customers here are price-sensitive (${e.toFixed(1)}): a ${p > 0 ? "rise loses" : "cut wins"} revenue because trips move more than the price.`
      : "At exactly −1.0, revenue stays flat whatever the price: trips move one-for-one with price.";
    // revenue curve across the slider range, with the current point
    const xs = Array.from({ length: 61 }, (_, i) => i - 30);
    const ys = xs.map((x) => rows.reduce((s, b) => s + ((!only || b.tier === only) ? b.revenue * Math.pow(1 + x / 100, 1 + e) : b.revenue), 0));
    plot("c-sim", [
      { x: xs, y: ys, type: "scatter", mode: "lines", line: { color: C.xenon, width: 2 }, hovertemplate: "<b>%{y:,.0f}</b><br>price %{x:+d}%<extra></extra>" },
      { x: [Math.round(p * 100)], y: [r1], type: "scatter", mode: "markers", marker: { size: 14, color: C.brake, line: { color: theme().surface, width: 2 } }, hoverinfo: "skip" },
    ], { showlegend: false, margin: { t: 10, r: 10, b: 36, l: 64 }, xaxis: { ticksuffix: "%", title: "Price change", fixedrange: true },
      yaxis: { tickprefix: "₦", fixedrange: true },
      shapes: [{ type: "line", x0: 0, x1: 0, yref: "paper", y0: 0, y1: 1, line: { color: theme().muted, dash: "dot", width: 1 } }] }, { displayModeBar: false });
  }

  // export + CSV upload
  $("#export").onclick = async (e) => {
    e.preventDefault();
    const res = await fetch("/api/admin/analytics/export.csv", { headers: { Authorization: `Bearer ${session.get().token}` } });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "oyibo_rentals_export.csv" });
    a.click(); URL.revokeObjectURL(url);
  };
  $("#csv").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    const o = $("#csv-out");
    o.innerHTML = `<div class="skeleton"></div>`;
    try {
      const r = await api("/api/admin/analytics/upload", { method: "POST", form });
      o.innerHTML = `<div class="kpis"><div><span>Total charges</span><b>${naira(r.kpis.total_revenue)}</b></div><div><span>Rentals</span><b>${r.kpis.rental_count}</b></div>
        <div><span>Average days</span><b>${r.kpis.average_days.toFixed(1)}</b></div><div><span>Currently rented</span><b>${r.kpis.active_count}</b></div>
        <div><span>Speeding events</span><b>${r.kpis.speeding_events}</b></div></div><div class="charts">${coreCharts("u-")}</div>`;
      drawCore("u-", r);
    } catch (err) { o.innerHTML = `<p style="color:var(--alert)">${esc(err.message)}</p>`; }
  };

  const onTheme = () => { if (rep && !rep.empty && !rep.no_match) draw(); };
  window.addEventListener("themechange", onTheme);
  await refresh();
  return () => { window.removeEventListener("themechange", onTheme); observer?.disconnect(); map?.remove(); };
}
