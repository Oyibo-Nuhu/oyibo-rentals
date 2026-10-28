import { api, naira } from "./api.js";
import { vehiclePhoto } from "./art.js";
import { $, $$, MODE_INFO, esc, fmtDate, render, state, syncMe, toast } from "./app.js";

const STATUS_TEXT = { active: "On the road", reserved: "Upcoming", completed: "Completed", cancelled: "Cancelled", pending_payment: "Awaiting payment" };

export function makeMap(el, opts = {}) {
  const map = L.map(el, { scrollWheelZoom: false, ...opts }).setView([6.5, 3.4], 11);
  let tiles;
  // Tile server comes from the backend (MAP_TILE_URL), defaulting to OpenStreetMap.
  // Night theme darkens the tiles with a CSS filter, so one tile set works for both themes.
  const setTiles = () => {
    tiles?.remove();
    const m = state.meta?.map || {};
    tiles = L.tileLayer(m.tile_url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: m.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19, className: "oy-tiles",
    }).addTo(map);
  };
  setTiles();
  const onTheme = () => setTiles();
  window.addEventListener("themechange", onTheme);
  map.on("unload", () => window.removeEventListener("themechange", onTheme));
  return map;
}

export function carIcon(over) {
  return L.divIcon({ className: "", html: `<div class="car-marker ${over ? "over" : ""}"></div>`, iconSize: [18, 18], iconAnchor: [9, 9] });
}

export function countdownText(ms) {
  const neg = ms < 0, s = Math.floor(Math.abs(ms) / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${neg ? "+" : ""}${d ? d + "d " : ""}${pad(h)}:${pad(m)}:${pad(sec)}`;
}

export async function tripsView() {
  render(`<h1 style="font-size:clamp(1.8rem,4vw,2.8rem)">My trips</h1><div class="trip-list" id="list"><div class="skeleton" style="height:90px"></div></div>`);
  let rows;
  try { rows = await api("/api/rentals/mine"); } catch (e) { toast(e.message, "error"); return; }
  if (!rows.length) {
    $("#list").innerHTML = `<div class="empty"><p>No trips yet. Pick a ride and your bookings will show up here.</p><a class="btn btn-primary" href="#/fleet">Find a ride</a></div>`;
    return;
  }
  const order = { active: 0, reserved: 1, pending_payment: 2, completed: 3, cancelled: 4 };
  rows.sort((a, b) => order[a.status] - order[b.status]);
  $("#list").innerHTML = rows.map((r) => `
    <a class="trip" href="#/trips/${esc(r.code)}">
      <div class="art">${vehiclePhoto(r.vehicle, { credit: false })}</div>
      <div><h3>${esc(r.vehicle.brand)} ${esc(r.vehicle.model)}</h3>
        <div class="muted" style="font-size:.9rem">${MODE_INFO[r.mode].label}${r.pickup ? ` · ${esc(r.pickup)} → ${esc(r.dropoff)}` : ""} · ${fmtDate(r.start_at)}</div></div>
      <div style="text-align:right"><span class="status ${r.status}">${STATUS_TEXT[r.status]}</span>
        <div class="money" style="margin-top:6px">${naira(r.final_cost ?? r.total_due)}</div></div>
    </a>`).join("");
}

export async function tripView(code) {
  let r;
  try { r = await api(`/api/rentals/${encodeURIComponent(code)}`); }
  catch (e) { render(`<div class="empty"><h2>Trip not found</h2><p>${esc(e.message)}</p><a class="btn" href="#/trips">My trips</a></div>`); return; }

  const v = r.vehicle;
  const live = r.status === "active";
  const head = `
    <a href="#/trips" class="muted">← My trips</a>
    <div style="display:flex;justify-content:space-between;align-items:end;gap:16px;flex-wrap:wrap;margin:14px 0 22px">
      <div><span class="status ${r.status}">${STATUS_TEXT[r.status]}</span>
        <h1 style="font-size:clamp(1.6rem,3.6vw,2.6rem);margin-top:10px">${esc(v.brand)} ${esc(v.model)}</h1>
        <p class="muted" style="margin:0">${esc(r.code)} · ${MODE_INFO[r.mode].label}${r.pickup ? ` · ${esc(r.pickup)} → ${esc(r.dropoff)}` : ""}${r.destination ? ` · ${esc(r.destination)}` : ""} · Plate ${esc(v.plate)}</p></div>
      <div class="trip-photo">${vehiclePhoto(v, { credit: "link" })}</div>
    </div>`;

  const owed = r.pending_payments.map((p) => `<a class="btn btn-primary btn-sm" href="#/pay/${esc(p.reference)}">Pay ${p.kind === "installment" ? "remaining instalment" : "balance"} ${naira(p.amount)}</a>`).join(" ");

  if (live) {
    render(`${head}
      <div class="grid-2">
        <div><div class="live-map" id="map"></div>
          <p class="hint">Live position updates every few seconds. Speed limit: ${state.meta.speed_limit} km/h.</p></div>
        <div class="panel">
          <p class="muted" style="margin:0" id="cd-label">Time left</p>
          <div class="countdown" id="cd">--:--:--</div>
          <div class="ring" id="ring"><i></i></div>
          <p class="hint" id="cd-end">Ends ${fmtDate(r.end_at)}</p>
          <div class="speedo" id="speedo"><b id="speed">0</b><span class="muted">km/h</span></div>
          <p class="muted" id="loc" style="margin:4px 0 0">Awaiting signal</p>
          <div class="stat-row">
            <div><span>Distance</span><b id="dist">${r.distance_km} km</b></div>
            <div><span>Included</span><b>${r.quote.included_km} km</b></div>
            <div><span>${v.is_electric ? "Battery" : "Fuel"}</span><b id="fuel">${v.fuel_level}%</b></div>
            <div><span>Speed alerts</span><b id="spd">${r.speeding_events}</b></div>
          </div>
          ${r.with_driver ? `<p class="hint">One of our drivers is at the wheel, so speeding never counts against you.</p>` : `
          <div class="strikes" id="strikes" aria-live="polite"></div>`}
          ${owed ? `<p>${owed}</p>` : ""}
          <button class="btn btn-danger sos" id="sos">SOS: I need help</button>
          <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
            <button class="btn btn-primary" id="end">End trip</button>
            <button class="btn btn-ghost" id="damage">Report damage</button>
          </div>
        </div>
      </div>`);

    const map = makeMap($("#map"));
    const path = L.polyline([], { color: getComputedStyle(document.documentElement).getPropertyValue("--flip").trim(), weight: 4 }).addTo(map);
    let marker = null, fitted = false;
    if (r.quote.route?.pickup_coords) {
      L.circleMarker(r.quote.route.pickup_coords, { radius: 6, color: "#FF2E63" }).addTo(map).bindTooltip(r.pickup);
      L.circleMarker(r.quote.route.dropoff_coords, { radius: 6, color: "#B79CFF" }).addTo(map).bindTooltip(r.dropoff);
    }
    const start = new Date(r.start_at).getTime(), end = new Date(r.end_at).getTime();
    let lastOver = false;

    const tickClock = () => {
      if (!$("#cd") || !$("#ring")) { clearInterval(clock); clearInterval(poll); return; } // page was redrawn
      const left = end - Date.now();
      $("#cd").textContent = countdownText(left);
      $("#cd").classList.toggle("over", left < 0);
      $("#cd-label").textContent = left < 0 ? "Overtime (late charges apply)" : "Time left";
      $("#ring").style.setProperty("--p", Math.max(0, Math.min(100, ((Date.now() - start) / (end - start)) * 100)));
    };
    const pol = state.meta.speeding_policy || { free_strikes: 3, fee: 5000 };
    let lastStrikes = r.speeding_events;
    function paintStrikes(n) {
      const box = $("#strikes"); if (!box) return;
      const extra = Math.max(0, n - pol.free_strikes);
      box.innerHTML = Array.from({ length: pol.free_strikes }, (_, i) => `<i class="${i < n ? "on" : ""}" title="Warning ${i + 1}"></i>`).join("")
        + `<i class="fee ${extra ? "on" : ""}" title="Charged incidents"></i>`
        + `<span>${n < pol.free_strikes ? `${n} of ${pol.free_strikes} speeding warnings used` : n === pol.free_strikes ? `All ${pol.free_strikes} warnings used: the next one costs ${naira(pol.fee)}` : `${extra} charged incident${extra > 1 ? "s" : ""}: ${naira(extra * pol.fee)}`}</span>`;
      if (n > lastStrikes) document.getElementById("speedo")?.classList.add("over");
      lastStrikes = n;
    }
    paintStrikes(r.speeding_events);
    const update = (t) => {
      const pts = t.track || [];
      if (!pts.length) return;
      path.setLatLngs(pts.map((p) => [p.lat, p.lng]));
      const last = pts[pts.length - 1];
      if (!marker) marker = L.marker([last.lat, last.lng], { icon: carIcon(last.over_limit) }).addTo(map);
      marker.setLatLng([last.lat, last.lng]);
      marker.setIcon(carIcon(last.over_limit));
      if (!fitted) { map.fitBounds(path.getBounds().pad(0.6), { maxZoom: 14 }); fitted = true; }
      $("#speed").textContent = Math.round(last.speed);
      $("#speedo").classList.toggle("over", last.over_limit);
      $("#loc").textContent = last.location;
      $("#dist").textContent = `${t.distance_km} km`;
      $("#fuel").textContent = `${t.vehicle.fuel_level}%`;
      $("#spd").textContent = t.speeding_events;
      paintStrikes(t.speeding_events);
      if (last.over_limit && !lastOver) toast(`Slow down: ${Math.round(last.speed)} km/h is over the ${state.meta.speed_limit} km/h limit.`, "error");
      lastOver = last.over_limit;
      if (t.status !== "active") location.reload();
    };
    update(r);
    tickClock();
    const clock = setInterval(tickClock, 1000);
    const poll = setInterval(async () => { try { update(await api(`/api/rentals/${encodeURIComponent(code)}`)); } catch {} }, 4000);

    $("#sos").onclick = async () => {
      if (!confirm("Send an SOS to the Oyibo response team with your location?")) return;
      try { const res = await api(`/api/rentals/${code}/sos`, { method: "POST", body: { message: "Help needed during trip." } }); toast(res.message, "ok"); }
      catch (e) { toast(e.message, "error"); }
    };
    $("#end").onclick = async () => {
      if (!confirm("End this trip now? Charges for extra distance or late return will be calculated.")) return;
      try { await api(`/api/rentals/${code}/end`, { method: "POST" }); toast("Trip ended. Thanks for riding with Oyibo!", "ok"); tripView(code); }
      catch (e) { toast(e.message, "error"); }
    };
    $("#damage").onclick = () => damageDialog(code);
    return () => { clearInterval(clock); clearInterval(poll); map.remove(); };
  }

  if (r.status === "reserved" || r.status === "pending_payment") {
    const pay = r.status === "pending_payment";
    render(`${head}
      <div class="panel" style="max-width:620px">
        <p class="muted" style="margin:0">${pay ? "Complete payment to reserve this vehicle" : "Your trip starts in"}</p>
        ${pay ? `<div class="pay-amount" style="font-size:2.4rem">${naira(r.total_due)}</div>` : `<div class="countdown" id="cd">--:--:--</div>`}
        <p class="hint">${fmtDate(r.start_at)} → ${fmtDate(r.end_at)}</p>
        ${owed ? `<p>${owed}</p>` : ""}
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">
          ${pay ? `<a class="btn btn-primary" href="#/fleet">Choose again</a>` : ""}
          <button class="btn btn-ghost" id="cancel">Cancel booking</button>
        </div>
      </div>`);
    let clock;
    if (!pay) {
      const start = new Date(r.start_at).getTime();
      clock = setInterval(() => {
        if (!$("#cd")) { clearInterval(clock); return; }
        const left = start - Date.now();
        $("#cd").textContent = countdownText(Math.max(0, left));
        if (left <= 0) { clearInterval(clock); setTimeout(() => tripView(code), 2500); }
      }, 1000);
    }
    $("#cancel").onclick = async () => {
      if (!confirm("Cancel this booking?")) return;
      try { const res = await api(`/api/rentals/${code}/cancel`, { method: "POST" }); toast(res.message, "ok"); tripView(code); }
      catch (e) { toast(e.message, "error"); }
    };
    return () => clearInterval(clock);
  }

  // completed or cancelled
  const s = r.settlement;
  render(`${head}
    <div class="grid-2">
      <div class="panel">
        ${s ? `
          <h2>Trip summary</h2>
          <div class="stat-row">
            <div><span>Distance</span><b>${s.actual_km} km</b></div>
            <div><span>Top speed</span><b>${r.max_speed} km/h</b></div>
            <div><span>Speed alerts</span><b>${r.speeding_events}</b></div>
            <div><span>Late</span><b>${s.late_units} ${s.late_unit_label}</b></div>
          </div>
          <dl style="display:grid;grid-template-columns:1fr auto;gap:8px">
            <dt class="muted">Paid at booking</dt><dd>${naira(r.total_due, 2)}</dd>
            <dt class="muted">Extra distance (${s.extra_km} km)</dt><dd>${naira(s.mileage_charge, 2)}</dd>
            <dt class="muted">Late return</dt><dd>${naira(s.late_charge, 2)}</dd>
            ${s.speeding_charge ? `<dt class="muted">Speeding (${s.speeding_incidents} incidents, ${s.speeding_incidents - (state.meta.speeding_policy?.free_strikes ?? 3)} charged)</dt><dd style="color:var(--alert)">${naira(s.speeding_charge, 2)}</dd>` : ""}
            <dt class="muted">Deposit refund</dt><dd>${naira(s.deposit_refund, 2)}</dd>
            ${s.balance_due ? `<dt class="muted">Balance due</dt><dd style="color:var(--alert)">${naira(s.balance_due, 2)}</dd>` : ""}
            <dt><b>Final cost</b></dt><dd class="money" style="color:var(--spark)">${naira(s.final_cost, 2)}</dd>
          </dl>
          ${owed ? `<p>${owed}</p>` : ""}` : `<h2>This booking was cancelled</h2><p class="muted">Nothing more to do here.</p>`}
      </div>
      ${r.status === "completed" ? `
      <div class="panel">
        <h2>How was the ride?</h2>
        <div id="stars" style="display:flex;gap:6px;font-size:2rem" role="group" aria-label="Rate this trip">
          ${[1, 2, 3, 4, 5].map((n) => `<button class="icon-btn" style="width:48px;height:48px;font-size:1.4rem;color:${(r.rating || 0) >= n ? "var(--spark)" : "var(--muted)"}" data-n="${n}" aria-label="${n} star${n > 1 ? "s" : ""}">★</button>`).join("")}
        </div>
        <p class="hint">Something got damaged? Report it and see what your ${state.meta.insurance[r.insurance_plan].label} cover pays.</p>
        <button class="btn btn-ghost" id="damage">Report damage</button>
        <a class="btn btn-primary" href="#/book/${esc(v.id)}" style="margin-left:6px">Book again</a>
      </div>` : ""}
    </div>`);
  $$("#stars button").forEach((b) => b.onclick = async () => {
    try { await api(`/api/rentals/${code}/rate`, { method: "POST", body: { rating: Number(b.dataset.n) } }); toast("Thanks for the rating!", "ok"); tripView(code); }
    catch (e) { toast(e.message, "error"); }
  });
  const dmg = $("#damage");
  if (dmg) dmg.onclick = () => damageDialog(code);
  syncMe();
}

function damageDialog(code) {
  const d = document.createElement("dialog");
  d.innerHTML = `
    <form method="dialog" id="dmg-form">
      <h2>Report damage</h2>
      <div class="field"><label for="dmg-desc">What happened?</label><textarea id="dmg-desc" rows="3" required minlength="5" placeholder="e.g. Scratched rear bumper while parking"></textarea></div>
      <div class="field"><label for="dmg-cost">Estimated repair cost (₦)</label><input id="dmg-cost" type="number" min="1" required></div>
      <div id="dmg-result"></div>
      <div style="display:flex;gap:10px;justify-content:end">
        <button class="btn btn-ghost" value="cancel" formnovalidate>Close</button>
        <button class="btn btn-primary" id="dmg-submit" value="default">Submit report</button>
      </div>
    </form>`;
  document.body.append(d);
  d.showModal();
  d.addEventListener("close", () => d.remove());
  $("#dmg-submit", d).onclick = async (e) => {
    e.preventDefault();
    const description = $("#dmg-desc", d).value.trim(), damage_cost = Number($("#dmg-cost", d).value);
    if (description.length < 5 || !(damage_cost > 0)) { toast("Describe the damage and enter a repair cost.", "error"); return; }
    try {
      const res = await api(`/api/rentals/${code}/claims`, { method: "POST", body: { description, damage_cost } });
      $("#dmg-result", d).innerHTML = `<div class="demo-banner" style="color:var(--text)">Claim #${res.claim_id} submitted.<br>
        Insurance pays <b>${naira(res.insurer_pays)}</b>. Your part: <b>${naira(res.customer_pays)}</b> (excess ${naira(res.excess)}).<br>We'll review it and contact you.</div>`;
      $("#dmg-submit", d).remove();
    } catch (err) { toast(err.message, "error"); }
  };
}
