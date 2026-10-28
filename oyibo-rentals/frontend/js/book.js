import { api, naira, session } from "./api.js";
import { vehiclePhoto } from "./art.js";
import { $, $$, MODE_INFO, esc, fmtDate, render, state, syncMe, toast } from "./app.js";
import { makeMap } from "./trips.js";
import { mascotCar } from "./launch.js";
import { sound } from "./sound.js";

const INSURANCE_ORDER = ["basic", "standard", "premium"];

function localInputValue(date) {
  const d = new Date(date.toLocaleString("en-US", { timeZone: "Africa/Lagos" }));
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export async function bookView(vehicleId, params) {
  let v;
  try { v = await api(`/api/fleet/${encodeURIComponent(vehicleId)}`); }
  catch (e) { render(`<div class="empty"><h2>Vehicle not found</h2><p>${esc(e.message)}</p><a class="btn" href="#/fleet">Back to fleet</a></div>`); return; }

  const zones = state.meta.zones;
  const zoneOpts = (sel) => `<option value="">Choose a location</option>` +
    zones.map((z) => `<option value="${z.key}" ${z.key === sel ? "selected" : ""}>${esc(z.name)}</option>`).join("");
  const minPlan = INSURANCE_ORDER.indexOf(v.min_insurance);
  const form = {
    mode: params.get("mode") || "route",
    pickup: params.get("pickup") || "", dropoff: params.get("dropoff") || "", destination: "",
    days: 1, start: "", insurance_plan: v.min_insurance, with_driver: false, payment_plan: "full",
  };
  const allowed = v.allowed_modes || Object.keys(MODE_INFO);
  if (!allowed.includes(form.mode)) form.mode = allowed[0];

  render(`
    <a href="#/fleet" class="muted">← Back to fleet</a>
    <div class="steps" aria-hidden="true" style="margin-top:16px"><span class="done"></span><span id="s2"></span><span id="s3"></span><span></span></div>
    <div class="grid-2">
      <div>
        <h1 style="font-size:clamp(1.6rem,3.6vw,2.6rem)">${esc(v.brand)} ${esc(v.model)}</h1>
        <p class="muted">${esc(v.tier_label)} · ${v.year} · ${v.seats} seats${v.is_electric ? " · Electric" : ""} · Plate ${esc(v.plate)}</p>

        <section class="panel" style="margin-top:20px">
          <h2>How do you want to rent?</h2>
          <div class="choices" id="modes">
            ${Object.entries(MODE_INFO).map(([k, m]) => { const ok = allowed.includes(k);
              return `<button type="button" class="choice" data-mode="${k}" aria-pressed="${form.mode === k}" ${ok ? "" : "disabled"}><strong>${m.label}</strong><span>${ok ? m.blurb : `Not available for ${esc(v.tier_label)}`}</span></button>`; }).join("")}
          </div>
        </section>

        <section class="panel" style="margin-top:18px">
          <h2>Where and when</h2>
          <div class="row" id="route-fields">
            <div class="field"><label for="pickup">Pickup</label><select id="pickup">${zoneOpts(form.pickup)}</select></div>
            <div class="field"><label for="dropoff">Drop-off</label><select id="dropoff">${zoneOpts(form.dropoff)}</select></div>
          </div>
          <div class="field" id="dest-field" hidden><label for="destination">Destination (for the estimate)</label>
            <select id="destination"><option value="">Not sure yet</option>${state.meta.destinations.map((d) => `<option value="${d.key}">${esc(d.name)} · ${d.distance_km} km</option>`).join("")}</select></div>
          <div class="row">
            <div class="field"><label for="start">Start</label><input id="start" type="datetime-local" value="${localInputValue(new Date())}">
              <div class="hint">Lagos time. Leave as now to start right away. Weekday rush hours cost 20% more on route and half-day trips.</div></div>
            <div class="field" id="days-field" hidden><label for="days">Number of days</label><input id="days" type="number" min="1" max="90" value="1"></div>
          </div>
        </section>

        <section class="panel" style="margin-top:18px">
          <h2>Damage insurance</h2>
          <div class="choices" id="plans">
            ${INSURANCE_ORDER.map((k, i) => { const p = state.meta.insurance[k]; const off = i < minPlan;
              return `<button type="button" class="choice" data-plan="${k}" aria-pressed="${form.insurance_plan === k}" ${off ? "disabled style='opacity:.4'" : ""}>
                <strong>${p.label}</strong><span>${Math.round(p.rate * 100)}% of rental. Covers up to ${naira(p.cover_cap)}, you pay the first ${naira(p.excess)}.${off ? " Not available for this class." : ""}</span></button>`; }).join("")}
          </div>
          <label class="toggle"><input type="checkbox" id="driver"> Add a professional driver</label>
          <div id="lic-slot" aria-live="polite"></div>
          <div id="plan-field" hidden>
            <h3 style="margin-top:12px">Payment plan</h3>
            <div class="choices" id="pay-plans">
              <button type="button" class="choice" data-pp="full" aria-pressed="true"><strong>Pay in full</strong><span>One payment now.</span></button>
              <button type="button" class="choice" data-pp="installments" aria-pressed="false"><strong>Pay small small</strong><span>Deposit plus 40% now, the rest before your rental ends.</span></button>
            </div>
          </div>
        </section>
      </div>

      <aside class="panel receipt" aria-live="polite">
        <div class="art receipt-photo">${vehiclePhoto(v, { credit: "link", eager: true })}</div>
        <div id="receipt-body"><p class="muted">Fill in the details to see your price.</p></div>
        <div class="mini-map" id="mini-map" hidden></div>
        <button class="btn btn-primary btn-block" id="book-btn" style="margin-top:16px" disabled>Continue to payment</button>
        <p class="hint" style="text-align:center">You won't be charged until you confirm payment.</p>
      </aside>
    </div>`);

  let map = null, layer = null, timer = 0, seq = 0, lastQuote = null, selfDrive = { ok: true };
  try { selfDrive = (await api("/api/me/licence")).self_drive; } catch {}
  const blockedByLicence = () => !form.with_driver && !selfDrive.ok;
  function licenceNote() {
    const slot = $("#lic-slot"); if (!slot) return;
    if (form.with_driver) { slot.innerHTML = ""; return; }
    slot.innerHTML = selfDrive.ok
      ? `<p class="lic-ok">✓ Self-drive: your licence is on file${selfDrive.status === "verified" ? " and verified" : ""}.</p>`
      : `<div class="lic-gate"><p><b>Driving yourself needs a full driver's licence.</b> ${esc(selfDrive.reason)} Learner's permits aren't accepted.</p>
          <div><a class="btn btn-sm btn-primary" href="#/profile?licence=1" id="lic-add">Add my licence</a><button type="button" class="btn btn-sm btn-ghost" id="lic-driver">Add a driver instead</button></div></div>`;
    $("#lic-add")?.addEventListener("click", () => sessionStorage.setItem("oy-after-licence", location.hash));
    $("#lic-driver")?.addEventListener("click", () => { $("#driver").checked = true; form.with_driver = true; requote(); });
  }

  function syncFields() {
    $("#route-fields").hidden = form.mode !== "route";
    $("#dest-field").hidden = form.mode !== "cross_country";
    $("#days-field").hidden = !["full_day", "cross_country"].includes(form.mode);
  }

  function lines(q) {
    const row = (label, value, neg) => value ? `<dt>${label}</dt><dd>${neg ? "−" : ""}${naira(value)}</dd>` : "";
    const unit = q.unit_label === "hours" ? `${q.units} hr${q.units > 1 ? "s" : ""}` : `${q.units} day${q.units > 1 ? "s" : ""}`;
    return `
      <h3>${MODE_INFO[q.mode].label} · ${unit}</h3>
      <p class="muted" style="font-size:.9rem;margin:0">${fmtDate(q.start_at)} → ${fmtDate(q.end_at, { timeStyle: "short", dateStyle: q.unit_label === "days" ? "medium" : undefined })}</p>
      ${q.route?.pickup ? `<p style="margin:8px 0 0;font-size:.9rem">${esc(q.route.pickup)} → ${esc(q.route.dropoff)} · ${q.route.distance_km} km · about ${Math.round(q.route.drive_hours * 60)} min driving</p>` : ""}
      <dl>
        ${row("Rental", q.base_cost)}${row("Multi-day discount", q.discount, true)}${row("Rush-hour pricing", q.peak_surcharge)}
        ${row("Green ride discount", q.ev_discount, true)}${row("Driver", q.driver_fee)}
        ${row(state.meta.insurance[q.insurance_plan].label + " insurance", q.insurance_fee)}${row("Interstate pack", q.interstate_fee)}
        ${row("VAT (7.5%)", q.vat)}${row("Refundable deposit", q.security_deposit)}
        <dt class="total">Total</dt><dd class="total"></dd>
      </dl>
      <span class="total-amount" id="total">${naira(q.total_due)}</span>
      <p class="hint" style="margin-top:0">Includes ${q.included_km} km. Extra km: ${naira(v.mileage_rate)}/km. Deposit refunded after return.</p>
      ${q.notes.length ? `<ul class="notes">${q.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      ${q.available ? "" : `<p style="color:var(--alert)">This vehicle is already booked for that time. Try a different start time.</p>`}`;
  }

  function showRoute(q) {
    const box = $("#mini-map");
    if (!q?.route?.pickup_coords || !window.L) { box.hidden = true; return; }
    box.hidden = false;
    if (!map) map = makeMap(box, { zoomControl: false, attributionControl: true });
    if (layer) layer.remove();
    const a = q.route.pickup_coords, b = q.route.dropoff_coords;
    layer = L.layerGroup([
      L.polyline([a, b], { color: getComputedStyle(document.documentElement).getPropertyValue("--flip").trim() || "#B79CFF", weight: 4, dashArray: "8 8" }),
      L.circleMarker(a, { radius: 7, color: "#FF2E63", fillOpacity: 1 }),
      L.circleMarker(b, { radius: 7, color: "#B79CFF", fillOpacity: 1 }),
    ]).addTo(map);
    setTimeout(() => { map.invalidateSize(); map.fitBounds([a, b], { padding: [30, 30] }); }, 50);
  }

  async function requote() {
    const my = ++seq;
    syncFields();
    const body = {
      vehicle_id: v.id, mode: form.mode, insurance_plan: form.insurance_plan, with_driver: form.with_driver,
      start_at: form.start ? form.start + ":00+01:00" : null,
    };
    if (form.mode === "route") Object.assign(body, { pickup: form.pickup, dropoff: form.dropoff });
    if (["full_day", "cross_country"].includes(form.mode)) body.days = Number(form.days) || 0;
    if (form.mode === "cross_country" && form.destination) body.destination = form.destination;
    if (form.mode === "route" && (!form.pickup || !form.dropoff)) {
      $("#receipt-body").innerHTML = `<p class="muted">Choose a pickup and drop-off to see the time and price.</p>`;
      $("#book-btn").disabled = true; $("#s2").className = ""; showRoute(null); return;
    }
    try {
      const q = await api("/api/quote", { method: "POST", body });
      if (my !== seq) return;
      lastQuote = q;
      $("#receipt-body").innerHTML = lines(q);
      requestAnimationFrame(() => { const t = $("#total"); t?.classList.add("bump"); setTimeout(() => t?.classList.remove("bump"), 250); });
      $("#book-btn").disabled = !q.available || blockedByLicence();
      licenceNote();
      $("#s2").className = "done"; $("#s3").className = "done";
      $("#plan-field").hidden = !q.installments_allowed;
      if (!q.installments_allowed) setPlan("full");
      showRoute(q);
    } catch (e) {
      if (my !== seq) return;
      lastQuote = null;
      $("#receipt-body").innerHTML = `<p style="color:var(--alert)">${esc(e.message)}</p>`;
      $("#book-btn").disabled = true;
    }
  }
  const later = () => { clearTimeout(timer); timer = setTimeout(requote, 250); };

  function setPlan(pp) {
    form.payment_plan = pp;
    $$("#pay-plans .choice").forEach((b) => b.setAttribute("aria-pressed", b.dataset.pp === pp));
  }

  $$("#modes .choice").forEach((b) => b.onclick = () => {
    form.mode = b.dataset.mode;
    $$("#modes .choice").forEach((x) => x.setAttribute("aria-pressed", x === b));
    requote();
  });
  $$("#plans .choice").forEach((b) => b.onclick = () => {
    if (b.disabled) return;
    form.insurance_plan = b.dataset.plan;
    $$("#plans .choice").forEach((x) => x.setAttribute("aria-pressed", x === b));
    requote();
  });
  $$("#pay-plans .choice").forEach((b) => b.onclick = () => setPlan(b.dataset.pp));
  $("#pickup").onchange = (e) => { form.pickup = e.target.value; requote(); };
  $("#dropoff").onchange = (e) => { form.dropoff = e.target.value; requote(); };
  $("#destination").onchange = (e) => { form.destination = e.target.value; requote(); };
  $("#start").oninput = (e) => { form.start = e.target.value; later(); };
  $("#days").oninput = (e) => { form.days = e.target.value; later(); };
  $("#driver").onchange = (e) => { form.with_driver = e.target.checked; requote(); };
  form.start = $("#start").value;

  $("#book-btn").onclick = async () => {
    if (!lastQuote) return;
    const btn = $("#book-btn");
    btn.disabled = true; btn.textContent = "Reserving…";
    try {
      const body = {
        vehicle_id: v.id, mode: form.mode, insurance_plan: form.insurance_plan, with_driver: form.with_driver,
        start_at: form.start + ":00+01:00", payment_plan: form.payment_plan,
        days: Number(form.days) || 1, pickup: form.pickup || null, dropoff: form.dropoff || null,
        destination: form.destination || null,
      };
      const res = await api("/api/rentals", { method: "POST", body });
      location.hash = `#/pay/${res.payment.reference}`;
    } catch (e) {
      toast(e.message, "error");
      btn.disabled = false; btn.textContent = "Continue to payment";
    }
  };

  requote();
  return () => { clearTimeout(timer); map?.remove(); };
}

// ---------- payment ----------
const CHANNELS = [
  ["card", "Card", "Visa, Mastercard or Verve"],
  ["bank_transfer", "Bank transfer", "Pay into a one-time account"],
  ["ussd", "USSD", "Dial a code from your bank"],
];

export async function payView(reference) {
  render(`<div class="pay-wrap"><div class="processing"><div class="road"></div><p class="muted">Opening checkout…</p></div></div>`);
  let co;
  try { co = await api(`/api/payments/${reference}/checkout`, { method: "POST" }); }
  catch (e) { render(`<div class="empty"><h2>Can't open checkout</h2><p>${esc(e.message)}</p><a class="btn" href="#/trips">My trips</a></div>`); return; }

  if (co.mode === "done") { location.hash = `#/success/${reference}`; return; }
  if (co.mode === "paystack") {
    render(`<div class="pay-wrap panel"><h2>Pay securely with Paystack</h2>
      <p class="muted">You'll choose card, bank transfer or USSD on Paystack, then come straight back here.</p>
      <a class="btn btn-primary btn-block" href="${esc(co.url)}">Continue to Paystack</a></div>`);
    return;
  }

  let channel = "card";
  render(`
    <div class="pay-wrap">
      <div class="panel">
        <p class="muted" style="margin:0">Amount to pay</p>
        <div class="pay-amount">${(() => { const [whole, kobo] = naira(co.amount, 2).split("."); return `${whole}<small>${kobo ? "." + kobo : ""}</small>`; })()}</div>
        <div class="demo-banner">Demo checkout: no money moves. Add a Paystack key on the server to take real payments.</div>
        <h3>Pay with</h3>
        <div class="choices" id="channels" style="margin-bottom:18px">
          ${CHANNELS.map(([k, l, d]) => `<button type="button" class="choice" data-ch="${k}" aria-pressed="${k === channel}"><strong>${l}</strong><span>${d}</span></button>`).join("")}
        </div>
        <button class="btn btn-primary btn-block" id="pay-btn">Pay ${naira(co.amount)}</button>
        <p class="hint" style="text-align:center">Reference ${esc(reference)}</p>
      </div>
    </div>`);
  $$("#channels .choice").forEach((b) => b.onclick = () => {
    channel = b.dataset.ch;
    $$("#channels .choice").forEach((x) => x.setAttribute("aria-pressed", x === b));
  });
  $("#pay-btn").onclick = async () => {
    $(".pay-wrap .panel").innerHTML = `<div class="processing"><div class="road"></div><h3>Confirming your payment…</h3><p class="muted">Hold on small.</p></div>`;
    try {
      await new Promise((r) => setTimeout(r, 1500));
      await api(`/api/payments/${reference}/demo-confirm`, { method: "POST", body: { channel } });
      location.hash = `#/success/${reference}`;
    } catch (e) {
      toast(e.message, "error");
      setTimeout(() => (location.hash = "#/trips"), 1500);
    }
  };
}

export async function payReturnView(params) {
  const ref = params.get("reference");
  render(`<div class="pay-wrap"><div class="processing"><div class="road"></div><p class="muted">Checking your payment with Paystack…</p></div></div>`);
  try {
    const res = await api(`/api/payments/${encodeURIComponent(ref)}/verify`);
    if (res.status === "success") { location.hash = `#/success/${ref}`; return; }
    render(`<div class="empty"><h2>Payment not confirmed yet</h2><p>If you completed payment, it can take a minute to confirm. Check again shortly.</p>
      <button class="btn btn-primary" onclick="location.reload()">Check again</button> <a class="btn btn-ghost" href="#/pay/${esc(ref)}">Try paying again</a></div>`);
  } catch (e) {
    render(`<div class="empty"><h2>We couldn't check that payment</h2><p>${esc(e.message)}</p><a class="btn" href="#/trips">My trips</a></div>`);
  }
}

export async function successView(reference) {
  let res;
  try { res = await api(`/api/payments/${reference}/verify`); }
  catch (e) { render(`<div class="empty"><h2>Payment not found</h2><p>${esc(e.message)}</p></div>`); return; }
  if (res.status !== "success") { location.hash = `#/pay/${reference}`; return; }
  const r = res.rental, v = r.vehicle;
  const first = session.user?.name?.split(" ")[0] || "";
  render(`
    <section class="success">
      <div class="drive-by" aria-hidden="true"><div class="mascot celebrate">${mascotCar()}</div></div>
      <h1>Oya${first ? ", " + esc(first) : ""}! You're set.</h1>
      <p class="muted" style="margin:0 auto 18px">${esc(v.brand)} ${esc(v.model)} is ${r.status === "active" ? "yours now. Your timer has started." : "reserved for you."}</p>
      <span class="points-burst">+<b id="pts">0</b> Oyibo points</span>
      <div class="panel success-card">
        <dl style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0">
          <dt class="muted">Booking</dt><dd style="margin:0">${esc(r.code)}</dd>
          <dt class="muted">Trip</dt><dd style="margin:0">${MODE_INFO[r.mode].label}${r.pickup ? `: ${esc(r.pickup)} → ${esc(r.dropoff)}` : ""}</dd>
          <dt class="muted">Starts</dt><dd style="margin:0">${fmtDate(r.start_at)}</dd>
          <dt class="muted">Ends</dt><dd style="margin:0">${fmtDate(r.end_at)}</dd>
          <dt class="muted">Paid</dt><dd style="margin:0">${naira(res.amount, 2)}</dd>
        </dl>
        ${r.pending_payments.length ? `<p class="hint">Balance of ${naira(r.pending_payments[0].amount)} is due before your rental ends.</p>` : ""}
        <div style="display:flex;gap:10px;margin-top:18px;flex-wrap:wrap">
          <a class="btn btn-primary" href="#/trips/${esc(r.code)}">${r.status === "active" ? "Track my trip" : "View booking"}</a>
          <a class="btn btn-ghost" href="#/fleet">Book another</a>
        </div>
      </div>
    </section>`);
  syncMe();
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) sound.driveIn(0.15);
  const target = res.points_earned, t0 = performance.now() + 1400;
  const tick = (t) => { const p = Math.min(1, Math.max(0, (t - t0) / 900)); const el = document.getElementById("pts");
    if (!el) return; el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))).toLocaleString(); if (p < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  if (window.confetti && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const colors = ["#FF2E63", "#B79CFF", "#FF8FB4", "#45E3A0", "#F4ECF1"];
    setTimeout(() => {
      confetti({ particleCount: 140, spread: 90, origin: { y: 0.45 }, colors });
      setTimeout(() => confetti({ particleCount: 60, angle: 60, spread: 60, origin: { x: 0 }, colors }), 300);
      setTimeout(() => confetti({ particleCount: 60, angle: 120, spread: 60, origin: { x: 1 }, colors }), 500);
    }, 900);
  }
}
