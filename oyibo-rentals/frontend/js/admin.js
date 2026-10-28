import { api, naira, session } from "./api.js";
import { $, $$, MODE_INFO, esc, fmtDate, render, state, toast } from "./app.js";
import { makeMap } from "./trips.js";
import { analyticsTab } from "./analytics.js";
import { vehiclePhoto } from "./art.js";
import { setBadge } from "./shell.js";

const TABS = [["ops", "Live GPS"], ["analytics", "Analytics"], ["fleet", "Fleet"], ["licences", "Licences"], ["claims", "Claims"], ["people", "Customers"]];

export async function adminView(tab) {
  const label = (TABS.find(([k]) => k === tab) || TABS[0])[1];
  render(`
    <p class="eyebrow" style="margin-bottom:6px">Control room</p>
    <h1 style="font-size:clamp(1.8rem,4vw,2.6rem);margin-bottom:22px">${label}</h1>
    <div id="admin-body"></div>`);
  const body = $("#admin-body");
  switch (tab) {
    case "ops": return opsTab(body);
    case "analytics": return analyticsTab(body);
    case "fleet": return fleetTab(body);
    case "claims": return claimsTab(body);
    case "people": return peopleTab(body);
    case "licences": return licencesTab(body);
    default: location.hash = "#/admin";
  }
}

// ---------- live GPS tracking ----------
const tierColour = (t) => getComputedStyle(document.documentElement).getPropertyValue(`--t-${t}`).trim() || "#B79CFF";

function gpsIcon(c, selected) {
  const over = c.over_limit;
  return L.divIcon({
    className: "gps-pin-wrap",
    html: `<div class="gps-pin ${over ? "over" : ""} ${selected ? "sel" : ""}" style="--c:${over ? "var(--hazard)" : tierColour(c.tier)}">
      <i></i><span>${Math.round(c.speed)}</span></div>`,
    iconSize: [44, 44], iconAnchor: [22, 22],
  });
}

function gauge(speed, limit) {
  const max = 160, r = 62, cx = 80, cy = 80;
  const ang = (v) => Math.PI * (1 - Math.min(v, max) / max);
  const pt = (v, rr = r) => [cx + rr * Math.cos(ang(v)), cy - rr * Math.sin(ang(v))];
  const arc = (a0, a1) => { const [x0, y0] = pt(a0), [x1, y1] = pt(a1); return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
  const [nx, ny] = pt(speed, r - 12);
  return `<svg viewBox="0 0 160 96" class="gauge" role="img" aria-label="Speed ${Math.round(speed)} km/h">
    <path d="${arc(0, limit)}" class="g-track"/><path d="${arc(limit, max)}" class="g-red"/>
    <path d="${arc(0, Math.min(speed, max))}" class="g-fill ${speed > limit ? "over" : ""}"/>
    <line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" class="g-needle"/><circle cx="${cx}" cy="${cy}" r="5" class="g-hub"/>
    <text x="${cx}" y="${cy - 18}" class="g-val">${Math.round(speed)}</text><text x="${cx}" y="${cy - 4}" class="g-unit">km/h</text>
    <text x="${pt(limit, r + 10)[0]}" y="${pt(limit, r + 10)[1]}" class="g-lim">${limit}</text></svg>`;
}

async function opsTab(body) {
  const limit = state.meta.speed_limit;
  body.innerHTML = `
    <div class="gps-head"><span class="live-badge"><i></i>LIVE</span><span class="muted" id="gps-updated"></span></div>
    <div class="kpis" id="ops-kpis"></div>
    <div class="gps-grid">
      <div class="gps-mapbox"><div class="live-map" id="ops-map"></div>
        <p class="hint">Pins show live speed in km/h, coloured by vehicle class. Red pulsing pins are over ${limit} km/h. Click a pin or a vehicle to follow it.</p></div>
      <aside class="panel gps-side" id="gps-side"></aside>
    </div>
    <div class="gps-lower">
      <div class="panel"><h2>Alerts</h2><div class="alert-feed" id="alerts"></div></div>
      <div class="panel"><h2>Active rentals</h2><div class="table-wrap"><table id="active-table"></table></div></div>
    </div>`;

  const map = makeMap($("#ops-map"), { scrollWheelZoom: true });
  const pins = new Map(), trails = new Map(), history = new Map();
  let live = [], selected = null, follow = true, filter = "all", search = "", fitted = false, seenAlerts = null, detail = null, selTrack = null, raf = 0;

  // smooth movement: glide each pin from its last position to the new one
  const glides = new Map();
  function glide(code, to) {
    const m = pins.get(code); if (!m) return;
    const from = m.getLatLng();
    glides.set(code, { from, to: L.latLng(to), t0: performance.now() });
    if (!raf) raf = requestAnimationFrame(step);
  }
  function step(t) {
    for (const [code, g] of glides) {
      const p = Math.min(1, (t - g.t0) / 1200), e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      pins.get(code)?.setLatLng([g.from.lat + (g.to.lat - g.from.lat) * e, g.from.lng + (g.to.lng - g.from.lng) * e]);
      if (p >= 1) glides.delete(code);
    }
    raf = glides.size ? requestAnimationFrame(step) : 0;
  }

  const visible = () => live.filter((c) => (filter === "all" || (filter === "speeding" && c.over_limit) || (filter === "overdue" && c.overdue) || (filter === "fuel" && c.fuel_level < 20))
    && (!search || [c.vehicle, c.plate, c.code, c.customer, c.location].some((x) => String(x || "").toLowerCase().includes(search))));

  function sideList() {
    const rows = visible();
    $("#gps-side").innerHTML = `
      <div class="box-head"><h3 style="margin:0">On the road (${live.length})</h3></div>
      <input type="search" id="gps-q" placeholder="Search vehicle, plate, customer" value="${esc(search)}" aria-label="Search active rentals" style="margin:10px 0">
      <div class="seg seg-sm" id="gps-filter" role="group" aria-label="Show">
        ${[["all", "All"], ["speeding", "Speeding"], ["overdue", "Overdue"], ["fuel", "Low fuel"]].map(([k, l]) => `<button data-f="${k}" aria-pressed="${filter === k}">${l}</button>`).join("")}
      </div>
      <div class="gps-list">${rows.map((c) => `
        <button class="gps-item ${c.over_limit ? "over" : ""}" data-sel="${esc(c.code)}">
          <i class="dot" style="background:${tierColour(c.tier)}"></i>
          <span><b>${esc(c.vehicle)}</b><small>${esc(c.plate)} · ${esc(c.location)}</small></span>
          <em class="${c.over_limit ? "over" : ""}">${Math.round(c.speed)}<small>km/h</small></em>
        </button>`).join("") || `<p class="muted" style="margin-top:14px">${live.length ? "Nothing matches this filter." : "No vehicles on the road right now."}</p>`}</div>`;
    $("#gps-q").oninput = (e) => { search = e.target.value.trim().toLowerCase(); const pos = e.target.selectionStart; sideList(); const q = $("#gps-q"); q.focus(); q.setSelectionRange(pos, pos); };
    $$("#gps-filter button").forEach((b) => b.onclick = () => { filter = b.dataset.f; sideList(); });
    $$("[data-sel]", $("#gps-side")).forEach((b) => b.onclick = () => select(b.dataset.sel));
  }

  function sideDetail() {
    const c = live.find((x) => x.code === selected);
    if (!c) { selected = null; sideList(); return; }
    const r = detail, left = new Date(c.end_at).getTime() - Date.now();
    const hms = (ms) => { const s = Math.abs(Math.floor(ms / 1000)); return `${left < 0 ? "−" : ""}${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
    const speeds = (selTrack || []).map((p) => p.speed).slice(-60);
    const sw = 260, sh = 50, smax = Math.max(limit + 20, ...speeds, 1);
    const sx = (i) => (i / Math.max(1, speeds.length - 1)) * sw, sy = (v) => sh - (v / smax) * sh;
    $("#gps-side").innerHTML = `
      <button class="linkish" id="gps-back">← All vehicles</button>
      <div class="gps-detail">
        ${r ? `<div class="gps-photo">${vehiclePhoto(r.vehicle, { credit: false })}</div>` : ""}
        <h3 style="margin:10px 0 0">${esc(c.vehicle)}</h3>
        <p class="muted" style="margin:0 0 6px">${esc(c.plate)} · ${esc(c.code)} · ${MODE_INFO[c.mode].label}</p>
        ${gauge(c.speed, limit)}
        <p class="gps-loc ${c.over_limit ? "over" : ""}">${c.over_limit ? "Over the speed limit · " : ""}<b>${esc(c.location)}</b></p>
        <div class="stat-row gps-stats">
          <div><span>Time left</span><b id="gps-left" class="${left < 0 ? "over" : ""}">${hms(left)}</b></div>
          <div><span>Distance</span><b>${c.distance_km} km</b></div>
          <div><span>Speed alerts</span><b>${c.speeding_events}</b></div>
          <div><span>${c.is_electric ? "Battery" : "Fuel"}</span><b>${c.fuel_level}%</b><i class="fuel"><s style="width:${c.fuel_level}%"></s></i></div>
        </div>
        ${speeds.length > 1 ? `<h4>Speed, last ${speeds.length} readings</h4>
          <svg viewBox="0 0 ${sw} ${sh}" class="gps-spark" preserveAspectRatio="none" aria-hidden="true">
            <line x1="0" x2="${sw}" y1="${sy(limit)}" y2="${sy(limit)}" class="lim"/>
            <polyline points="${speeds.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(" ")}"/></svg>` : ""}
        ${r ? `<p class="gps-cust"><span class="muted">Customer</span> <b>${esc(r.customer.name)}</b> · <a href="tel:${esc(r.customer.phone)}">${esc(r.customer.phone)}</a></p>` : ""}
        <label class="toggle"><input type="checkbox" id="gps-follow" ${follow ? "checked" : ""}> Keep the map on this vehicle</label>
        <div class="strikes">${[0, 1, 2].map((i) => `<i class="${i < c.speeding_events ? "on" : ""}"></i>`).join("")}<i class="fee ${c.speeding_events > 3 ? "on" : ""}"></i>
          <span>${c.speeding_events} speeding incident${c.speeding_events === 1 ? "" : "s"}${c.speeding_events > 3 ? ` · ${naira((c.speeding_events - 3) * (state.meta.speeding_policy?.fee ?? 5000))} charged` : ""}</span></div>
        <button class="btn btn-primary btn-block" id="gps-warn" ${r?.with_driver ? "disabled title='An Oyibo driver is on this trip'" : ""}>Send speed warning</button>
        <button class="btn btn-ghost btn-block" data-end="${esc(c.code)}" style="margin-top:8px">End this rental</button>
      </div>`;
    $("#gps-back").onclick = () => select(null);
    $("#gps-follow").onchange = (e) => { follow = e.target.checked; };
    bindEnd($("#gps-side"));
    $("#gps-warn")?.addEventListener("click", async (e) => {
      const b = e.currentTarget; b.disabled = true;
      try { const res = await api(`/api/admin/rentals/${encodeURIComponent(c.code)}/warn`, { method: "POST", body: {} }); toast(`Speed warning sent. ${res.message}`, "ok"); b.textContent = "Warning sent ✓"; }
      catch (err) { toast(err.message, "error"); b.disabled = false; }
    });
  }

  function drawSelTrack() {
    trails.get("__sel")?.remove(); trails.delete("__sel");
    if (!selTrack || selTrack.length < 2) return;
    const segs = L.layerGroup();
    for (let i = 1; i < selTrack.length; i++) {
      const a = selTrack[i - 1], b = selTrack[i];
      L.polyline([[a.lat, a.lng], [b.lat, b.lng]], { color: b.over_limit ? cssVarHazard() : tierColour(live.find((x) => x.code === selected)?.tier), weight: 5, opacity: .9 }).addTo(segs);
    }
    segs.addTo(map); trails.set("__sel", segs);
  }
  const cssVarHazard = () => getComputedStyle(document.documentElement).getPropertyValue("--hazard").trim() || "#FF5A1F";

  async function select(code) {
    selected = code; detail = null; selTrack = null;
    pins.forEach((m, k) => { const c = live.find((x) => x.code === k); if (c) m.setIcon(gpsIcon(c, k === selected)); });
    if (!code) { trails.get("__sel")?.remove(); trails.delete("__sel"); sideList(); return; }
    follow = true;
    const c = live.find((x) => x.code === code);
    if (c?.lat != null) map.flyTo([c.lat, c.lng], Math.max(map.getZoom(), 14), { duration: .8 });
    sideDetail();
    try { detail = await api(`/api/rentals/${encodeURIComponent(code)}`); selTrack = detail.track; if (selected === code) { drawSelTrack(); sideDetail(); } } catch {}
  }

  function bindEnd(root) {
    $$("[data-end]", root).forEach((b) => b.onclick = async () => {
      if (!confirm(`End rental ${b.dataset.end} now and settle charges?`)) return;
      try { const s = await api(`/api/admin/rentals/${b.dataset.end}/end`, { method: "POST" }); toast(`Ended. Final cost ${naira(s.final_cost)}.`, "ok"); if (selected === b.dataset.end) selected = null; refresh(); }
      catch (e) { toast(e.message, "error"); }
    });
  }

  async function refresh() {
    let alerts;
    try { [live, alerts] = await Promise.all([api("/api/tracking/live"), api("/api/tracking/alerts")]); } catch { return; }
    if (!body.isConnected) return;
    $("#gps-updated").textContent = `Updated ${new Date().toLocaleTimeString("en-NG", { timeZone: "Africa/Lagos", hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    const speeding = live.filter((x) => x.over_limit).length;
    $("#ops-kpis").innerHTML = `
      <div><span>On the road</span><b>${live.length}</b></div>
      <div><span>Over ${limit} km/h now</span><b style="color:${speeding ? "var(--alert)" : "inherit"}">${speeding}</b></div>
      <div><span>Overdue returns</span><b>${live.filter((x) => x.overdue).length}</b></div>
      <div><span>Open alerts</span><b>${alerts.filter((a) => !a.resolved).length}</b></div>
      <div><span>Low fuel or battery</span><b>${live.filter((x) => x.fuel_level < 20).length}</b></div>`;

    const keep = new Set();
    for (const c of live) {
      if (c.lat == null) continue;
      keep.add(c.code);
      const h = history.get(c.code) || []; h.push([c.lat, c.lng]); if (h.length > 25) h.shift(); history.set(c.code, h);
      let m = pins.get(c.code);
      if (!m) {
        m = L.marker([c.lat, c.lng], { icon: gpsIcon(c, c.code === selected), riseOnHover: true }).addTo(map);
        m.on("click", () => select(c.code));
        pins.set(c.code, m);
      } else { m.setIcon(gpsIcon(c, c.code === selected)); glide(c.code, [c.lat, c.lng]); }
      m.bindTooltip(`<b>${esc(c.vehicle)}</b> · ${esc(c.plate)}<br>${Math.round(c.speed)} km/h · ${esc(c.location)}`, { direction: "top", offset: [0, -18] });
      let tr = trails.get(c.code);
      if (!tr) { tr = L.polyline(h, { color: tierColour(c.tier), weight: 3, opacity: .45, dashArray: "2 6" }).addTo(map); trails.set(c.code, tr); }
      else tr.setLatLngs(h);
    }
    for (const [code, m] of pins) if (!keep.has(code)) { m.remove(); pins.delete(code); trails.get(code)?.remove(); trails.delete(code); history.delete(code); }
    if (!fitted && pins.size) { map.fitBounds(L.featureGroup([...pins.values()]).getBounds().pad(0.3), { maxZoom: 13 }); fitted = true; }

    if (selected) {
      const c = live.find((x) => x.code === selected);
      if (c && selTrack) { selTrack.push({ lat: c.lat, lng: c.lng, speed: c.speed, over_limit: c.over_limit }); if (selTrack.length > 120) selTrack.shift(); drawSelTrack(); }
      if (c && follow) map.panTo([c.lat, c.lng], { animate: true, duration: 1 });
      sideDetail();
    } else if (!document.activeElement?.matches?.("#gps-q")) sideList();

    $("#alerts").innerHTML = alerts.length ? alerts.map((a) => `
      <div class="alert-item ${a.kind} ${a.resolved ? "resolved" : ""}">
        <time>${fmtDate(a.created_at, { timeStyle: "short", dateStyle: "short" })} · <button class="linkish" data-sel="${esc(a.rental)}">${esc(a.rental)}</button> · ${a.kind === "sos" ? "SOS" : a.kind === "speeding" ? "Speeding" : "Low fuel"}</time>
        ${esc(a.message)}
        ${a.resolved ? "" : `<div><button class="btn btn-sm btn-ghost" data-resolve="${a.id}" style="margin-top:8px">Mark handled</button></div>`}
      </div>`).join("") : `<p class="muted">No alerts. All quiet on the roads.</p>`;
    $$("[data-resolve]").forEach((b) => b.onclick = async () => { await api(`/api/admin/alerts/${b.dataset.resolve}/resolve`, { method: "POST" }); refresh(); });
    $$("#alerts [data-sel]").forEach((b) => b.onclick = () => { if (live.some((x) => x.code === b.dataset.sel)) select(b.dataset.sel); else toast("That rental has ended."); });
    if (seenAlerts !== null) alerts.filter((a) => a.id > seenAlerts && !a.resolved).slice(0, 2).forEach((a) => toast(a.message, "error"));
    seenAlerts = Math.max(0, ...alerts.map((a) => a.id));

    $("#active-table").innerHTML = `<thead><tr><th>Booking</th><th>Customer</th><th>Vehicle</th><th>Trip</th><th>Speed</th><th>Distance</th><th>Alerts</th><th>Due back</th><th></th></tr></thead><tbody>
      ${live.map((c) => `<tr class="${c.code === selected ? "sel" : ""}"><td><button class="linkish" data-sel="${esc(c.code)}">${esc(c.code)}</button></td><td>${esc(c.customer)}</td><td>${esc(c.vehicle)}</td><td>${MODE_INFO[c.mode].label}</td>
        <td style="color:${c.over_limit ? "var(--alert)" : "inherit"}">${c.speed} km/h</td><td>${c.distance_km} km</td><td>${c.speeding_events}</td>
        <td style="color:${c.overdue ? "var(--alert)" : "inherit"}">${fmtDate(c.end_at, { timeStyle: "short", dateStyle: "short" })}</td>
        <td><button class="btn btn-sm btn-ghost" data-end="${esc(c.code)}">End</button></td></tr>`).join("") || `<tr><td colspan="9" class="muted">No active rentals.</td></tr>`}</tbody>`;
    $$("#active-table [data-sel]").forEach((b) => b.onclick = () => { select(b.dataset.sel); window.scrollTo({ top: 0, behavior: "smooth" }); });
    bindEnd($("#active-table"));
  }
  await refresh();
  const t = setInterval(refresh, 4000);
  const clock = setInterval(() => { const el = $("#gps-left"); const c = live.find((x) => x.code === selected); if (!el || !c) return;
    const left = new Date(c.end_at).getTime() - Date.now(), s = Math.abs(Math.floor(left / 1000));
    el.textContent = `${left < 0 ? "−" : ""}${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; el.classList.toggle("over", left < 0); }, 1000);
  return () => { clearInterval(t); clearInterval(clock); cancelAnimationFrame(raf); map.remove(); };
}

const STATUS_LABEL = { available: "Available", unavailable: "Unavailable", maintenance: "In workshop", rented: "On a trip" };

async function uploadPhoto(vehicleId, file) {
  const form = new FormData();
  form.append("file", file);
  return api(`/api/admin/fleet/${encodeURIComponent(vehicleId)}/photo`, { method: "POST", form });
}

async function fleetTab(body) {
  let fleet = await api("/api/fleet");
  if (!body.isConnected) return;
  let tier = "", q = "";
  body.innerHTML = `
    <div class="fleet-admin">
      <form class="panel fa-form" id="add-form" novalidate hidden>
        <div class="box-head"><div><h2 style="margin-bottom:2px">Add a vehicle</h2>
          <p class="muted" style="margin:0">Create a new slot in any class. It goes live in the fleet as soon as you save.</p></div>
          <button type="button" class="btn btn-ghost btn-sm" id="fa-add-close">Close</button></div>
        <div class="fa-form-grid"><div class="fa-form-media">
        <label class="photo-drop" id="f-drop" for="f-photo">
          <input type="file" id="f-photo" accept="image/jpeg,image/png,image/webp" hidden>
          <span id="f-photo-preview"><b>Add a photo</b><small>Drop an image here or click to choose. JPG, PNG or WebP, up to 6 MB.</small></span>
        </label>
        <h3>Preview</h3>
        <div class="fa-preview" id="f-preview"></div>
        </div><div class="fa-form-fields">
        <div class="row"><div class="field"><label for="f-id">Vehicle ID</label><input id="f-id" required placeholder="e.g. EX-009" autocapitalize="characters"></div>
          <div class="field"><label for="f-tier">Class</label><select id="f-tier">${state.meta.tiers.map((t) => `<option value="${t.key}">${esc(t.label)}</option>`).join("")}</select></div></div>
        <div class="row"><div class="field"><label for="f-brand">Brand</label><input id="f-brand" required placeholder="Toyota"></div>
          <div class="field"><label for="f-model">Model</label><input id="f-model" required placeholder="Venza"></div></div>
        <div class="row"><div class="field"><label for="f-year">Year</label><input id="f-year" type="number" value="2024" min="1990" max="2030" required></div>
          <div class="field"><label for="f-rate">Daily rate (₦)</label><input id="f-rate" type="number" min="1" placeholder="Class default"><div class="hint" id="f-rate-hint"></div></div></div>
        <div class="row"><div class="field"><label for="f-seats">Seats</label><input id="f-seats" type="number" value="5" min="1" max="60"></div>
          <div class="field"><label for="f-plate">Plate</label><input id="f-plate" placeholder="LND-482KJ" autocapitalize="characters"></div></div>
        <div class="row"><div class="field"><label for="f-color">Colour</label><input id="f-color" placeholder="Pearl White"></div>
          <div class="field"><label for="f-zone">Home location</label><select id="f-zone">${state.meta.zones.map((z) => `<option value="${z.key}">${esc(z.name)}</option>`).join("")}</select></div></div>
        <div class="row">
          <label class="toggle"><input type="checkbox" id="f-ev"> Electric vehicle</label>
          <label class="toggle"><input type="checkbox" id="f-hold"> Add as unavailable (not bookable yet)</label>
        </div>
        <button class="btn btn-primary btn-block" id="f-submit" style="margin-top:14px">Add vehicle</button>
        </div></div>
      </form>
      <div class="panel">
        <div class="box-head"><div><h2 style="margin-bottom:2px">Fleet (<span id="fa-count">${fleet.length}</span>)</h2>
          <p class="muted" style="margin:0">Set availability, change prices and photos. Unavailable or workshop vehicles can't be booked.</p></div>
          <div class="fa-tools"><input id="fa-q" type="search" placeholder="Search brand, model or ID" aria-label="Search fleet">
            <button type="button" class="btn btn-primary btn-sm" id="fa-add-toggle" aria-expanded="false" aria-controls="add-form">+ Add a vehicle</button></div></div>
        <div class="chips" id="fa-tiers" style="margin:14px 0">
          <button type="button" class="chip" data-tier="" aria-pressed="true">All</button>
          ${state.meta.tiers.map((t) => `<button type="button" class="chip" data-tier="${t.key}" aria-pressed="false">${esc(t.label.replace(/ \(.*\)/, ""))}</button>`).join("")}
        </div>
        <div class="fa-stats" id="fa-stats"></div>
        <div class="table-wrap"><table class="fa-table" id="fa-table"></table></div>
      </div>

    </div>
    <input type="file" id="fa-photo-input" accept="image/jpeg,image/png,image/webp" hidden>`;

  const toggleForm = (open) => {
    $("#add-form").hidden = !open; $("#fa-add-toggle").setAttribute("aria-expanded", open);
    if (open) { $("#add-form").scrollIntoView({ behavior: "smooth", block: "start" }); setTimeout(() => $("#f-id").focus({ preventScroll: true }), 350); }
  };
  $("#fa-add-toggle").onclick = () => toggleForm($("#add-form").hidden);
  $("#fa-add-close").onclick = () => toggleForm(false);
  const defaults = Object.fromEntries((state.meta.tiers || []).map((t) => [t.key, t]));
  function drawTable() {
    const term = q.trim().toLowerCase();
    const rows = fleet.filter((v) => (!tier || v.tier === tier) && (!term || [v.id, v.brand, v.model, v.tier_label, v.plate].some((x) => String(x).toLowerCase().includes(term))));
    const count = (s) => fleet.filter((v) => (!tier || v.tier === tier) && v.status === s).length;
    $("#fa-count").textContent = fleet.length;
    $("#fa-stats").innerHTML = ["available", "rented", "unavailable", "maintenance"].map((s) =>
      `<span class="fa-stat st-${s}"><b>${count(s)}</b> ${STATUS_LABEL[s].toLowerCase()}</span>`).join("");
    $("#fa-table").innerHTML = `<thead><tr><th>Vehicle</th><th>Class</th><th>Daily rate</th><th>Odometer</th><th>Availability</th></tr></thead><tbody>
      ${rows.map((v) => `<tr data-row="${esc(v.id)}">
        <td><div class="fa-veh">
          <button type="button" class="fa-thumb" data-photo="${esc(v.id)}" title="Change photo" aria-label="Change photo of ${esc(v.brand)} ${esc(v.model)}">
            ${v.photo ? `<img src="${esc(v.photo)}" alt="">` : `<span>+ photo</span>`}<i>Change</i></button>
          <div><b>${esc(v.brand)} ${esc(v.model)}</b> ${v.is_electric ? '<span class="tag ev">EV</span>' : ""}<small>${esc(v.id)} · ${esc(v.plate || "no plate")} · ${v.year}</small></div></div></td>
        <td>${esc(v.tier_label)}</td>
        <td><div class="fa-rate"><span>₦</span><input type="number" min="1" step="500" value="${v.daily_rate}" data-rate="${esc(v.id)}" aria-label="Daily rate for ${esc(v.brand)} ${esc(v.model)}"></div></td>
        <td>${v.odometer_km.toLocaleString()} km</td>
        <td>${v.status === "rented" ? `<span class="status active">On a trip</span>`
          : `<div class="seg seg-sm fa-avail" role="group" aria-label="Availability of ${esc(v.id)}">
              ${["available", "unavailable", "maintenance"].map((s) => `<button type="button" data-v="${esc(v.id)}" data-s="${s}" aria-pressed="${v.status === s}" class="as-${s}">${STATUS_LABEL[s]}</button>`).join("")}</div>`}</td>
      </tr>`).join("") || `<tr><td colspan="5" class="muted">No vehicles match.</td></tr>`}</tbody>`;
  }
  drawTable();

  const replace = (v) => { fleet = fleet.map((x) => (x.id === v.id ? { ...x, ...v } : x)); drawTable(); };
  $("#fa-q").oninput = (e) => { q = e.target.value; drawTable(); };
  $$("#fa-tiers .chip").forEach((c) => c.onclick = () => { tier = c.dataset.tier; $$("#fa-tiers .chip").forEach((x) => x.setAttribute("aria-pressed", x === c)); drawTable(); });

  // availability, price and photo, all inline (event delegation so redraws keep working)
  let photoTarget = null;
  $("#fa-table").addEventListener("click", async (e) => {
    const sb = e.target.closest("[data-s]");
    if (sb && sb.getAttribute("aria-pressed") !== "true") {
      try {
        const res = await api(`/api/admin/fleet/${encodeURIComponent(sb.dataset.v)}/status`, { method: "POST", body: { status: sb.dataset.s } });
        replace(res);
        toast(`${res.brand} ${res.model} is now ${STATUS_LABEL[res.status].toLowerCase()}.`, "ok");
        if (res.status !== "available" && res.upcoming_bookings?.length)
          toast(`Heads up: ${res.upcoming_bookings.length} upcoming booking(s) still use this vehicle (${res.upcoming_bookings.join(", ")}). Contact those customers or move them to another vehicle.`, "error");
      } catch (err) { toast(err.message, "error"); }
      return;
    }
    const pb = e.target.closest("[data-photo]");
    if (pb) { photoTarget = pb.dataset.photo; $("#fa-photo-input").click(); }
  });
  $("#fa-table").addEventListener("change", async (e) => {
    const inp = e.target.closest("[data-rate]");
    if (!inp) return;
    const value = Number(inp.value);
    if (!(value > 0)) { toast("Enter a daily rate above zero.", "error"); return; }
    try { const v = await api(`/api/admin/fleet/${encodeURIComponent(inp.dataset.rate)}/rate`, { method: "POST", body: { daily_rate: value } }); replace(v); toast(`Daily rate updated to ${naira(v.daily_rate)}. New bookings use the new price.`, "ok"); }
    catch (err) { toast(err.message, "error"); }
  });
  $("#fa-photo-input").onchange = async (e) => {
    const file = e.target.files[0]; e.target.value = "";
    if (!file || !photoTarget) return;
    const cell = $(`[data-photo="${CSS.escape(photoTarget)}"]`);
    cell?.classList.add("busy");
    try { const v = await uploadPhoto(photoTarget, file); replace(v); toast("Photo updated.", "ok"); }
    catch (err) { toast(err.message, "error"); cell?.classList.remove("busy"); }
  };

  // ----- add-a-vehicle form with photo and live preview -----
  let newPhoto = null;
  const drop = $("#f-drop");
  function setPhoto(file) {
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { toast("Use a JPG, PNG or WebP image.", "error"); return; }
    if (file.size > 6 * 1024 * 1024) { toast("That photo is over 6 MB. Pick a smaller one.", "error"); return; }
    newPhoto = file;
    const url = URL.createObjectURL(file);
    $("#f-photo-preview").innerHTML = `<img src="${url}" alt="Selected photo"><small>${esc(file.name)} · click to change</small>`;
    preview();
  }
  $("#f-photo").onchange = (e) => setPhoto(e.target.files[0]);
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setPhoto(e.dataTransfer.files[0]));

  function preview() {
    const t = $("#f-tier").value, rate = Number($("#f-rate").value) || null;
    $("#f-rate-hint").textContent = rate ? "" : `Leave empty to use the ${defaults[t]?.label || ""} default.`;
    const v = { id: $("#f-id").value.trim().toUpperCase() || "NEW-001", tier: t, tier_label: defaults[t]?.label || t,
      brand: $("#f-brand").value || "Brand", model: $("#f-model").value || "Model", color: $("#f-color").value,
      photo: newPhoto ? URL.createObjectURL(newPhoto) : null, photo_credit: null };
    $("#f-preview").innerHTML = `<div class="car fa-card"><div class="art">${vehiclePhoto(v, { credit: false })}</div>
      <div class="tags"><span class="tag">${esc(v.tier_label)}</span>${$("#f-ev").checked ? '<span class="tag ev">Electric</span>' : ""}${$("#f-hold").checked ? '<span class="tag busy">Unavailable</span>' : ""}</div>
      <h3>${esc(v.brand)} ${esc(v.model)}</h3><div class="meta">${esc($("#f-year").value)} · ${esc($("#f-seats").value)} seats${v.color ? " · " + esc(v.color) : ""}</div>
      <div class="price"><span class="money">${rate ? naira(rate) : "Class default"}<small class="muted"> a day</small></span></div></div>`;
  }
  $("#add-form").addEventListener("input", preview);
  preview();

  $("#add-form").onsubmit = async (e) => {
    e.preventDefault();
    const need = [["#f-id", "a vehicle ID"], ["#f-brand", "the brand"], ["#f-model", "the model"]].find(([sel]) => !$(sel).value.trim());
    if (need) { toast(`Enter ${need[1]}.`, "error"); $(need[0]).focus(); return; }
    const btn = $("#f-submit"); btn.disabled = true; btn.textContent = "Saving…";
    const rate = $("#f-rate").value;
    try {
      const res = await api("/api/admin/fleet", { method: "POST", body: {
        id: $("#f-id").value, tier: $("#f-tier").value, brand: $("#f-brand").value, model: $("#f-model").value,
        year: Number($("#f-year").value), daily_rate: rate ? Number(rate) : null, seats: Number($("#f-seats").value) || 4,
        plate: $("#f-plate").value, color: $("#f-color").value, home_zone: $("#f-zone").value, is_electric: $("#f-ev").checked } });
      let v = res.vehicle;
      if (newPhoto) { try { v = await uploadPhoto(v.id, newPhoto); } catch (err) { toast(`Vehicle added, but the photo failed: ${err.message}`, "error"); } }
      if ($("#f-hold").checked) v = await api(`/api/admin/fleet/${encodeURIComponent(v.id)}/status`, { method: "POST", body: { status: "unavailable" } });
      toast(res.message, "ok");
      fleetTab(body);
      setTimeout(() => $(`[data-row="${CSS.escape(v.id)}"]`)?.classList.add("flash"), 300);
    } catch (err) { toast(err.message, "error"); btn.disabled = false; btn.textContent = "Add vehicle"; }
  };
}

// ---------- claims ----------
async function claimsTab(body) {
  const rows = await api("/api/admin/claims");
  if (!body.isConnected) return;
  body.innerHTML = `<div class="panel"><h2>Damage claims</h2><div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Booking</th><th>Customer</th><th>Vehicle</th><th>Plan</th><th>Damage</th><th>Cost</th><th>Insurer pays</th><th>Customer pays</th><th>Status</th></tr></thead><tbody>
    ${rows.map((c) => `<tr><td>${fmtDate(c.created_at, { dateStyle: "medium" })}</td><td>${esc(c.rental)}</td><td>${esc(c.customer)}</td><td>${esc(c.vehicle)}</td>
      <td>${esc(state.meta.insurance[c.plan].label)}</td><td>${esc(c.description)}</td><td>${naira(c.damage_cost)}</td><td>${naira(c.insurer_pays)}</td><td>${naira(c.customer_pays)}</td>
      <td>${c.status === "open" ? `<button class="btn btn-sm btn-primary" data-c="${c.id}" data-s="approved">Approve</button> <button class="btn btn-sm btn-ghost" data-c="${c.id}" data-s="rejected">Reject</button>` : esc(c.status)}</td></tr>`).join("") || `<tr><td colspan="10" class="muted">No claims yet.</td></tr>`}
    </tbody></table></div></div>`;
  $$("[data-c]").forEach((b) => b.onclick = async () => {
    try { await api(`/api/admin/claims/${b.dataset.c}`, { method: "POST", body: { status: b.dataset.s } }); toast(`Claim ${b.dataset.s}.`, "ok"); claimsTab(body); }
    catch (e) { toast(e.message, "error"); }
  });
}

// ---------- driver's licences ----------
async function licencesTab(body) {
  const rows = await api("/api/admin/licences");
  if (!body.isConnected) return;
  const STATUS = { submitted: ["Waiting for review", "wait"], verified: ["Verified", "ok"], rejected: ["Rejected", "bad"] };
  const waiting = rows.filter((l) => l.status === "submitted").length;
  setBadge("licences", waiting);
  body.innerHTML = `
    <div class="panel">
      <div class="box-head"><div><h2 style="margin-bottom:2px">Driver's licences</h2>
        <p class="muted" style="margin:0">${waiting ? `${waiting} waiting for review.` : "Nothing waiting."} Customers can book self-drive once a full, unexpired licence is submitted; rejecting one blocks self-drive until they upload again. Learner's permits are refused automatically.</p></div></div>
      <div class="lic-queue">${rows.map((l) => `
        <article class="lic-item" data-id="${l.id}">
          <button class="lic-thumb" data-img="${l.id}" ${l.has_image ? "" : "disabled"} aria-label="View licence photo of ${esc(l.customer)}">${l.has_image ? "View photo" : "No photo"}</button>
          <div class="lic-info">
            <b>${esc(l.customer)}</b><small>${esc(l.email)} · ${esc(l.phone)}</small>
            <small>No. <b>${esc(l.number)}</b> · ${esc(l.state || "–")} · expires ${fmtDate(l.expires_on + "T00:00:00", { dateStyle: "medium" })}${l.expired ? ' <span style="color:var(--alert)">(expired)</span>' : ""}</small>
            ${l.review_note ? `<small>Note: ${esc(l.review_note)}</small>` : ""}
          </div>
          <span class="lic-pill ${STATUS[l.status][1]}">${STATUS[l.status][0]}</span>
          <div class="lic-actions">
            ${l.status !== "verified" ? `<button class="btn btn-sm btn-primary" data-review="verified">Verify</button>` : ""}
            ${l.status !== "rejected" ? `<button class="btn btn-sm btn-ghost" data-review="rejected">Reject</button>` : ""}
          </div>
        </article>`).join("") || `<p class="muted">No licences submitted yet.</p>`}</div>
    </div>
    <dialog id="lic-dlg"><div class="box-head"><h3 style="margin:0" id="lic-dlg-title">Licence photo</h3><button class="btn btn-sm btn-ghost" id="lic-dlg-close">Close</button></div>
      <img id="lic-dlg-img" alt="Driver's licence" style="width:100%;margin-top:12px;border-radius:12px"></dialog>`;

  $$("[data-img]", body).forEach((b) => b.onclick = async () => {
    const res = await fetch(`/api/admin/licences/${b.dataset.img}/image`, { headers: { Authorization: `Bearer ${session.get().token}` } });
    if (!res.ok) { toast("Couldn't load that photo.", "error"); return; }
    const url = URL.createObjectURL(await res.blob());
    const d = $("#lic-dlg"); $("#lic-dlg-img").src = url;
    $("#lic-dlg-title").textContent = `Licence of ${b.closest(".lic-item").querySelector(".lic-info b").textContent}`;
    d.showModal(); d.addEventListener("close", () => URL.revokeObjectURL(url), { once: true });
  });
  $("#lic-dlg-close").onclick = () => $("#lic-dlg").close();
  $$("[data-review]", body).forEach((b) => b.onclick = async () => {
    const id = b.closest(".lic-item").dataset.id, status = b.dataset.review;
    let note = "";
    if (status === "rejected") { note = prompt("Why is this licence rejected? The customer will see this.", "The photo is unclear."); if (note === null) return; }
    try { await api(`/api/admin/licences/${id}`, { method: "POST", body: { status, note } }); toast(status === "verified" ? "Licence verified. The customer has been told." : "Licence rejected. The customer has been told why.", "ok"); licencesTab(body); }
    catch (err) { toast(err.message, "error"); }
  });
}

async function peopleTab(body) {
  const rows = await api("/api/admin/users");
  if (!body.isConnected) return;
  body.innerHTML = `<div class="panel"><h2>Customers</h2><div class="table-wrap"><table>
    <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Trips</th><th>Points</th><th>Joined</th></tr></thead><tbody>
    ${rows.map((u) => `<tr><td>${esc(u.name)} ${u.demo ? '<span class="tag">demo</span>' : ""}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td>${u.trips}</td><td>${u.points.toLocaleString()}</td><td>${fmtDate(u.joined, { dateStyle: "medium" })}</td></tr>`).join("")}
    </tbody></table></div></div>`;
}
