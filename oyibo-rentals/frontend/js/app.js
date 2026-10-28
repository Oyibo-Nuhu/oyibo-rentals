import { api, session, naira } from "./api.js";
import { vehicleArt, vehiclePhoto } from "./art.js";
import { bookView, payView, payReturnView, successView } from "./book.js";
import { tripsView, tripView } from "./trips.js";
import { adminView } from "./admin.js";
import { mascotCar, launchSequence } from "./launch.js";
import { initShell, renderNav, refreshUserBadge } from "./shell.js";
import { profileView } from "./profile.js";
import { sound } from "./sound.js";

export const app = document.getElementById("app");
export const state = { meta: null };

// ---------- helpers ----------
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button"; close.className = "x-btn"; close.setAttribute("aria-label", "Close"); close.textContent = "×";
  el.append(text, close);
  document.getElementById("toasts").append(el);
  const dismiss = () => { if (el.classList.contains("leaving")) return; el.classList.add("leaving"); setTimeout(() => el.remove(), 200); };
  close.onclick = dismiss;
  let timer = setTimeout(dismiss, kind === "error" ? 6000 : 3800);
  // hovering keeps it open long enough to read; it closes shortly after the pointer leaves
  el.onmouseenter = () => clearTimeout(timer);
  el.onmouseleave = () => { timer = setTimeout(dismiss, 1500); };
}

export function render(html) {
  app.innerHTML = `<div class="view">${html}</div>`;
}

export const MODE_INFO = {
  route: { label: "Route", blurb: "A to B in Lagos, priced by the hour" },
  half_day: { label: "Half day", blurb: "6 hours, go anywhere" },
  full_day: { label: "Full day", blurb: "Daily rate, go anywhere" },
  cross_country: { label: "Cross country", blurb: "Leave Lagos, interstate cover" },
};

export function fmtDate(iso, opts = { dateStyle: "medium", timeStyle: "short" }) {
  return new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", ...opts });
}

export function requireLogin() {
  if (!session.user) {
    sessionStorage.setItem("oy-after-login", location.hash);
    location.hash = "#/login";
    return false;
  }
  return true;
}

export async function syncMe() {
  if (!session.user) return;
  try {
    const me = await api("/api/auth/me");
    session.set({ ...session.get(), user: me });
    refreshUserBadge();
  } catch {}
}

// ---------- home ----------
const PLANNER_ZONES = ["ikeja", "maryland", "gbagada", "magodo", "oshodi", "yaba", "surulere", "festac", "apapa",
  "ikoyi", "victoria-island", "lekki-phase-1", "ajah", "mmia", "ikorodu"];

const SHORT = { mmia: "Airport", "lekki-phase-1": "Lekki", "victoria-island": "VI", ikeja: "Ikeja" };

function homeView() {
  const zones = state.meta.zones.filter((z) => PLANNER_ZONES.includes(z.key));
  const W = 640, H = 380, pad = 40;
  const lats = zones.map((z) => z.lat), lngs = zones.map((z) => z.lng);
  const [minLat, maxLat, minLng, maxLng] = [Math.min(...lats), Math.max(...lats), Math.min(...lngs), Math.max(...lngs)];
  const px = (z) => [pad + ((z.lng - minLng) / (maxLng - minLng)) * (W - pad * 2), pad + ((maxLat - z.lat) / (maxLat - minLat)) * (H - pad * 2)];
  const opts = zones.map((z) => `<option value="${z.key}">${esc(z.name)}</option>`).join("");

  const first = session.user?.name?.split(" ")[0];
  render(`
    <section class="hero hero-calm">
      <div class="hero-copy">
        <p class="eyebrow">${first ? `Welcome back, ${esc(first)}` : "Lagos · cars, buses, trucks, bikes and kekes"}</p>
        <h1>Rent anything that <em>moves</em>.</h1>
        <p class="hero-lede">Pick two places on the map to see the time and price.</p>
        <div class="hero-ctas">
          <a class="btn btn-primary" href="#/fleet">Find a ride</a>
          ${session.user ? `<a class="btn btn-ghost" href="#/trips">My trips</a>` : `<a class="btn btn-ghost" href="#/signup">Create an account</a>`}
        </div>
      </div>
      <div class="planner">
        <svg viewBox="0 0 ${W} ${H}" aria-label="Lagos route planner map">
          <ellipse class="map-lagoon" cx="${W * 0.55}" cy="${H * 0.62}" rx="${W * 0.33}" ry="${H * 0.12}"/>
          ${zones.map((z) => { const [x, y] = px(z); return `<g data-zone="${z.key}"><circle class="map-dot" cx="${x}" cy="${y}" r="5"/><text class="map-label" x="${z.key === "mmia" ? x - 9 : x + 9}" y="${y + 4}" text-anchor="${z.key === "mmia" ? "end" : "start"}">${esc(SHORT[z.key] || z.name)}</text></g>`; }).join("")}
          <path id="route" class="route-path" d=""/>
          <circle id="route-car" class="route-car" r="8" cx="-20" cy="-20"/>
        </svg>
        <div class="planner-controls">
          <div><label for="from">From</label><select id="from">${opts}</select></div>
          <button class="icon-btn swap" id="swap" aria-label="Swap pickup and drop-off">⇄</button>
          <div><label for="to">To</label><select id="to">${opts}</select></div>
        </div>
        <div class="planner-readout" aria-live="polite">
          <div><div class="readout-big" id="r-hours">–</div><div class="readout-small">booked time</div></div>
          <div><div class="readout-big" id="r-price">–</div><div class="readout-small" id="r-note">Economy car, before deposit</div></div>
          <a class="btn btn-sm btn-primary" id="r-book" href="#/fleet" style="margin-left:auto">Book this route</a>
        </div>
      </div>
    </section>

    <section class="band">
      <div class="band-head"><h2>Choose your ride</h2><a class="linkish" href="#/fleet">See the whole fleet →</a></div>
      <div class="class-rail" id="class-rail">${state.meta.tiers.map(() => '<div class="class-card skeleton"></div>').join("")}</div>
    </section>

    <section class="band">
      <div class="band-head"><h2>Four ways to rent</h2><span class="muted">Corolla prices, VAT included</span></div>
      <div class="mode-cards">
        <a class="mode-card hot" href="#/fleet?mode=route"><b>Route</b><span>A to B, timed</span><em id="m-route">–</em></a>
        <a class="mode-card" href="#/fleet?mode=half_day"><b>Half day</b><span>6 hours, anywhere</span><em id="m-half">–</em></a>
        <a class="mode-card" href="#/fleet?mode=full_day"><b>Full day</b><span>Discounts from 7 days</span><em id="m-full">–</em></a>
        <a class="mode-card" href="#/fleet?mode=cross_country"><b>Cross country</b><span>Ibadan, Abuja and beyond</span><em id="m-cross">–</em></a>
      </div>
    </section>

    <section class="perks" aria-label="Included with every rental">
      <span>Live GPS on every trip</span><span>Card, transfer or USSD</span><span>Damage cover</span><span>Driver on request</span><span>SOS button</span>
    </section>`);

  // one card per vehicle class, with a real photo and the lowest daily rate
  api("/api/fleet").then((fleet) => {
    const rail = $("#class-rail"); if (!rail) return;
    rail.innerHTML = state.meta.tiers.map((t) => {
      const list = fleet.filter((v) => v.tier === t.key);
      if (!list.length) return "";
      const pick = list.find((v) => v.photo && v.status === "available") || list.find((v) => v.photo) || list[0];
      const from = Math.min(...list.map((v) => v.daily_rate));
      return `<a class="class-card" href="#/fleet?tier=${t.key}" style="--d:${state.meta.tiers.indexOf(t) * 60}ms">
        ${pick.photo ? `<img src="${esc(pick.photo)}" alt="" loading="lazy">` : `<div class="cc-art">${vehicleArt(pick.tier, pick.color, pick.brand + " " + pick.model)}</div>`}
        <span class="cc-text"><b>${esc(t.label.replace(/ \(.*\)/, ""))}</b><small>${list.length} · from ${naira(from)}/day</small></span></a>`;
    }).join("");
  }).catch(() => {});

  const from = $("#from"), to = $("#to");
  from.value = "lekki-phase-1"; to.value = "surulere";
  let raf = 0, seq = 0;

  function draw() {
    const a = zones.find((z) => z.key === from.value), b = zones.find((z) => z.key === to.value);
    $$("[data-zone] circle").forEach((c) => c.classList.toggle("on", [a.key, b.key].includes(c.parentNode.dataset.zone)));
    const [x1, y1] = px(a), [x2, y2] = px(b);
    const mx = (x1 + x2) / 2 + (y2 - y1) * 0.25, my = (y1 + y2) / 2 - (x2 - x1) * 0.25;
    const path = $("#route");
    path.setAttribute("d", `M${x1},${y1} Q${mx},${my} ${x2},${y2}`);
    const len = path.getTotalLength();
    path.style.transition = "none";
    path.style.strokeDasharray = len;
    path.style.strokeDashoffset = len;
    path.getBoundingClientRect();
    path.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1)";
    path.style.strokeDashoffset = 0;
    cancelAnimationFrame(raf);
    const car = $("#route-car"), t0 = performance.now();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = (t) => {
      const p = reduce ? 1 : ((t - t0) / 2600) % 1;
      const pt = path.getPointAtLength(p * len);
      car.setAttribute("cx", pt.x); car.setAttribute("cy", pt.y);
      if (!reduce) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    quote(a.key, b.key);
  }

  async function quote(a, b) {
    const my = ++seq;
    if (!$("#r-hours")) return;
    if (a === b) { $("#r-hours").textContent = "–"; $("#r-price").textContent = "Pick two places"; return; }
    try {
      const q = await api("/api/quote", { method: "POST", body: { vehicle_id: "EC-003", mode: "route", pickup: a, dropoff: b } });
      if (my !== seq || !$("#r-hours")) return;
      $("#r-hours").textContent = `${q.units} hrs`;
      $("#r-price").textContent = naira(q.subtotal + q.vat);
      $("#r-note").textContent = `${q.route.distance_km} km${q.peak_surcharge ? ", rush hour" : ""}. Economy car, before deposit`;
      $("#r-book").href = `#/fleet?mode=route&pickup=${a}&dropoff=${b}`;
    } catch (e) { const el = $("#r-price"); if (el) el.textContent = "–"; }
  }

  from.onchange = to.onchange = draw;
  $("#swap").onclick = () => { [from.value, to.value] = [to.value, from.value]; draw(); };
  draw();

  // sample prices on the mode strip
  const sample = (body, id) => api("/api/quote", { method: "POST", body: { vehicle_id: "EC-003", ...body } })
    .then((q) => { const el = $(id); if (el) el.textContent = naira(q.subtotal + q.vat); }).catch(() => {});
  sample({ mode: "route", pickup: "lekki-phase-1", dropoff: "surulere" }, "#m-route");
  sample({ mode: "half_day" }, "#m-half");
  sample({ mode: "full_day", days: 1 }, "#m-full");
  sample({ mode: "cross_country", days: 2, destination: "ibadan" }, "#m-cross");
  return () => cancelAnimationFrame(raf);
}

// ---------- auth ----------
const LINES = {
  login: ["Psst. Log in and I'll take you anywhere in Lagos.", "Back for another spin?", "Keys are on the hook. Just sign in."],
  register: ["New driver? Let's get you a plate.", "Fill this in and I'm all yours."],
  shy: "I'm not looking. Promise.",
  peek: "Okay… maybe a small peek.",
  nope: "Hmm, that key doesn't fit. Try again?",
  happy: "Looking good! Hit the button.",
};

const STRENGTH = [
  { label: "Engine off", note: "Use at least 8 characters." },
  { label: "Idling", note: "Add numbers or capitals." },
  { label: "Cruising", note: "Getting there. Try a symbol." },
  { label: "Highway", note: "Strong password." },
  { label: "Launch ready", note: "Excellent. Hard to guess." },
];

function pwScore(pw) {
  if (pw.length < 8) return 0;
  const extras = [/[a-z]/.test(pw) && /[A-Z]/.test(pw), /\d/.test(pw), /[^A-Za-z0-9]/.test(pw), pw.length >= 12].filter(Boolean).length;
  return Math.min(4, 1 + extras);
}

// Nigerian mobile: 10 digits after +234 (or 11 starting with 0), first digit 7, 8 or 9
function normalisePhone(raw) {
  let d = raw.replace(/\D/g, "");
  if (d.startsWith("234")) d = d.slice(3);
  if (d.startsWith("0")) d = d.slice(1);
  return /^[789][01]\d{8}$/.test(d) ? "0" + d : null;
}

function plateFor(name, phone) {
  const letters = (name.trim().split(/\s+/)[0] || "").replace(/[^a-z]/gi, "").toUpperCase().padEnd(3, "X").slice(0, 3);
  const digits = (phone.replace(/\D/g, "").slice(-3) || "").padStart(3, "0");
  return `${letters}-${digits}-OY`;
}

function authView(mode = "login") {
  if (session.user) { location.hash = "#/"; return; }
  const revArc = "M8 50 A40 40 0 0 1 88 50";
  render(`
    <section class="auth-stage">
      <div class="garage">
        <div class="garage-kicker">Oyibo Rentals · Lagos</div>
        <h1>Every ride starts with <em>a wink.</em></h1>
        <div class="mascot idle" id="mascot">${mascotCar()}</div>
        <p class="bubble" id="bubble" aria-live="polite"></p>
      </div>

      <div class="auth-card">
        <div class="auth-tabs" role="tablist" aria-label="Log in or create an account" data-side="${mode}">
          <span class="slider" aria-hidden="true"></span>
          <button role="tab" id="tab-login" aria-controls="login-form" data-side="login" aria-selected="${mode === "login"}">Log in</button>
          <button role="tab" id="tab-register" aria-controls="register-form" data-side="register" aria-selected="${mode === "register"}">Create account</button>
        </div>

        <div class="flip" id="flip" data-side="${mode}">
          <form class="face front" id="login-form" role="tabpanel" aria-labelledby="tab-login" novalidate>
            <div class="panel">
              <h2>Welcome back</h2>
              <p class="sub">Log in to book, track your trip and collect Oyibo points.</p>
              <div class="field"><label for="l-email">Email</label><input id="l-email" type="email" autocomplete="email" required></div>
              <div class="field"><label for="l-pass">Password</label>
                <div class="pw"><input id="l-pass" type="password" autocomplete="current-password" required data-shy>
                  <button type="button" class="reveal" data-for="l-pass" aria-pressed="false">Show</button></div></div>
              <button class="btn btn-primary btn-block" id="l-submit">Start the engine</button>
              <div class="auth-foot">
                <button type="button" class="demo-chip" id="demo-fill">Use the demo customer</button>
                <span class="muted">New here? <button type="button" class="linkish" data-goto="register">Create an account</button></span>
              </div>
            </div>
          </form>

          <form class="face back" id="register-form" role="tabpanel" aria-labelledby="tab-register" novalidate>
            <div class="panel">
              <h2>Get your keys</h2>
              <p class="sub">Takes a minute. You can book straight after.</p>
              <div class="plate-row">
                <div class="plate" aria-label="Your Oyibo plate preview"><small>LAGOS · OYIBO</small><strong id="plate">XXX-000-OY</strong></div>
                <p>Your plate number, made from your name and phone. It shows on your trips.</p>
              </div>
              <div class="field" id="f-name"><label for="r-name">Full name</label><input id="r-name" autocomplete="name" required minlength="2"><div class="err"></div></div>
              <div class="row">
                <div class="field" id="f-phone"><label for="r-phone">Phone number</label>
                  <div class="phone"><span>+234</span><input id="r-phone" inputmode="tel" autocomplete="tel-national" placeholder="803 937 8598" required></div><div class="err"></div></div>
                <div class="field" id="f-email"><label for="r-email">Email</label><input id="r-email" type="email" autocomplete="email" required><div class="err"></div></div>
              </div>
              <div class="field" id="f-pass"><label for="r-pass">Password</label>
                <div class="pw"><input id="r-pass" type="password" autocomplete="new-password" required minlength="8" maxlength="72" data-shy>
                  <button type="button" class="reveal" data-for="r-pass" aria-pressed="false">Show</button></div>
                <div class="rev" aria-live="polite">
                  <svg viewBox="0 0 96 58" aria-hidden="true">
                    <defs><linearGradient id="revGrad"><stop offset="0" style="stop-color:var(--xenon)"/><stop offset="1" style="stop-color:var(--brake)"/></linearGradient></defs>
                    <path class="arc" d="${revArc}"/><path class="arc-fill" id="rev-fill" d="${revArc}" pathLength="100" stroke-dasharray="100" stroke-dashoffset="100"/>
                    <g class="needle" id="rev-needle" style="transform:rotate(-90deg)"><line x1="48" y1="50" x2="48" y2="18"/></g>
                    <circle cx="48" cy="50" r="5" style="fill:var(--brake)"/>
                  </svg>
                  <div><b id="rev-label">Engine off</b><small id="rev-note">Use at least 8 characters.</small></div>
                </div></div>
              <div class="field" id="f-confirm"><label for="r-confirm">Confirm password</label><input id="r-confirm" type="password" autocomplete="new-password" required data-shy><div class="err"></div></div>
              <div class="field" id="f-ref"><label for="r-ref">Referral code <span class="muted">(optional)</span></label><input id="r-ref" placeholder="e.g. OYDEMO1" autocapitalize="characters"><div class="hint">You and your friend both get 500 Oyibo points.</div></div>
              <label class="check"><input type="checkbox" id="r-terms"> <span>I agree to the rental terms and to keep it under ${state.meta.speed_limit} km/h.</span></label>
              <button class="btn btn-primary btn-block" id="r-submit">Get my keys</button>
              <div class="auth-foot"><span class="muted">Already have an account? <button type="button" class="linkish" data-goto="login">Log in</button></span></div>
            </div>
          </form>
        </div>
      </div>
    </section>`);

  const mascot = $("#mascot"), bubble = $("#bubble"), flip = $("#flip"), tabs = $(".auth-tabs");
  let lineTimer = 0, moodTimer = 0;
  const say = (text) => {
    if (bubble.textContent === text) return;
    bubble.classList.add("swap");
    clearTimeout(lineTimer);
    lineTimer = setTimeout(() => { bubble.textContent = text; bubble.classList.remove("swap"); }, 160);
  };
  const mood = (m, ms) => {
    mascot.classList.remove("shy", "peek", "nope", "happy", "look");
    void mascot.offsetWidth;
    if (m) mascot.classList.add(m);
    clearTimeout(moodTimer);
    if (ms) moodTimer = setTimeout(() => { mascot.classList.remove(m); say(LINES[mode][0]); }, ms);
  };
  const fitHeight = () => {
    const face = flip.querySelector(mode === "login" ? ".front" : ".back");
    flip.style.height = face.offsetHeight + "px";
  };

  function setMode(next, focus = true) {
    mode = next;
    flip.dataset.side = tabs.dataset.side = mode;
    $$(".auth-tabs [role=tab]").forEach((t) => t.setAttribute("aria-selected", t.dataset.side === mode));
    $("#login-form").inert = mode !== "login";
    $("#register-form").inert = mode !== "register";
    history.replaceState(null, "", mode === "login" ? "#/login" : "#/signup");
    renderNav(mode === "login" ? "/login" : "/signup");
    mood(null);
    say(LINES[mode][Math.floor(Math.random() * LINES[mode].length)]);
    fitHeight();
    if (focus) setTimeout(() => $(mode === "login" ? "#l-email" : "#r-name")?.focus({ preventScroll: true }), 450);
  }
  $$(".auth-tabs [role=tab], [data-goto]").forEach((b) => b.onclick = () => setMode(b.dataset.side || b.dataset.goto));
  $(".auth-tabs").onkeydown = (e) => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) { setMode(mode === "login" ? "register" : "login"); $(`#tab-${mode}`).focus(); } };

  // the car shuts its eye while you type a password, and peeks if you press Show
  $$("[data-shy]").forEach((inp) => {
    inp.addEventListener("focus", () => { const shown = inp.type === "text"; mood(shown ? "peek" : "shy"); say(shown ? LINES.peek : LINES.shy); });
    inp.addEventListener("blur", () => { mood(null); say(LINES[mode][0]); });
  });
  $$(".reveal").forEach((b) => b.onclick = () => {
    const inp = document.getElementById(b.dataset.for);
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    b.textContent = show ? "Hide" : "Show";
    b.setAttribute("aria-pressed", show);
    inp.focus();
    mood(show ? "peek" : "shy"); say(show ? LINES.peek : LINES.shy);
  });
  $$("#l-email, #r-email, #r-name").forEach((inp) => inp.addEventListener("focus", () => mood("look")));

  $("#demo-fill").onclick = () => {
    $("#l-email").value = "demo@oyibo.ng"; $("#l-pass").value = "Demo1234!";
    mood("happy", 900); say("Demo keys loaded. Off we go?");
    $("#l-submit").focus();
  };

  // ----- register: live plate, rev meter, inline validation -----
  const setErr = (id, msg) => {
    const f = document.getElementById(id);
    f.classList.toggle("field-bad", !!msg);
    f.classList.toggle("field-ok", msg === "");
    const e = f.querySelector(".err"); if (e) e.textContent = msg || "";
  };
  function validate(show = false) {
    const name = $("#r-name").value.trim(), phone = $("#r-phone").value, email = $("#r-email").value.trim();
    const pw = $("#r-pass").value, confirm = $("#r-confirm").value;
    const errs = {
      "f-name": name.length < 2 ? "Enter your full name." : "",
      "f-phone": normalisePhone(phone) ? "" : "Enter a Nigerian mobile number, e.g. 803 937 8598.",
      "f-email": /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? "" : "Enter a valid email address.",
      "f-confirm": confirm && confirm === pw ? "" : "Passwords don't match yet.",
    };
    if (show) Object.entries(errs).forEach(([k, v]) => setErr(k, v));
    return { errs, ok: Object.values(errs).every((v) => !v) && pw.length >= 8 && $("#r-terms").checked };
  }
  let lastPlate = "";
  function updatePlate() {
    const p = plateFor($("#r-name").value, $("#r-phone").value);
    if (p === lastPlate) return;
    $("#plate").innerHTML = [...p].map((ch, i) => ch === lastPlate[i] ? esc(ch) : `<span>${esc(ch)}</span>`).join("");
    lastPlate = p;
  }
  function updateRev() {
    const pw = $("#r-pass").value, sc = pw ? pwScore(pw) : 0, pct = pw ? [12, 35, 60, 82, 100][sc] : 0;
    $("#rev-fill").style.strokeDashoffset = 100 - pct;
    $("#rev-needle").style.transform = `rotate(${-90 + pct * 1.8}deg)`;
    $("#rev-label").textContent = pw ? STRENGTH[sc].label : "Engine off";
    $("#rev-note").textContent = pw ? STRENGTH[sc].note : STRENGTH[0].note;
  }
  const touched = new Set();
  $("#register-form").addEventListener("input", (e) => {
    const f = e.target.closest(".field"); if (f) touched.add(f.id);
    updatePlate(); updateRev();
    const { errs, ok } = validate();
    touched.forEach((id) => { if (id in errs) setErr(id, errs[id]); });
    fitHeight();
    if (ok && !mascot.classList.contains("happy")) { mood("happy", 1200); say(LINES.happy); }
  });
  $("#r-terms").onchange = () => { if (validate().ok) { mood("happy", 1200); say(LINES.happy); } };

  // ----- submit both forms -----
  async function submit(kind, body, btn) {
    sound.unlock();   // this click lets the browser play the engine sound when the car drives off
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = kind === "login" ? "Checking keys…" : "Cutting your keys…";
    try {
      const data = await api(`/api/auth/${kind}`, { method: "POST", body });
      session.set(data);
      window.dispatchEvent(new Event("login"));
      const next = sessionStorage.getItem("oy-after-login");
      sessionStorage.removeItem("oy-after-login");
      await launchSequence({
        name: data.user.role === "admin" ? "Admin" : data.user.name, mode: kind,
        onReveal: () => { location.hash = next || (data.user.role === "admin" ? "#/admin" : "#/fleet"); },
      });
      if (kind === "register") toast(`Welcome aboard! Your referral code is ${data.user.referral_code}.`, "ok");
    } catch (err) {
      mood("nope", 1600); say(LINES.nope);
      toast(err.message, "error");
      btn.disabled = false; btn.textContent = label;
    }
  }
  $("#login-form").onsubmit = (e) => {
    e.preventDefault();
    const email = $("#l-email").value.trim(), password = $("#l-pass").value;
    if (!email || !password) { mood("nope", 1400); say("I need an email and a password first."); return; }
    submit("login", { email, password }, $("#l-submit"));
  };
  $("#register-form").onsubmit = (e) => {
    e.preventDefault();
    Object.keys(validate().errs).forEach((k) => touched.add(k));
    const { ok } = validate(true);
    fitHeight();
    const fieldsOk = Object.values(validate().errs).every((v) => !v) && $("#r-pass").value.length >= 8;
    if ($("#r-pass").value.length < 8) $("#f-pass").classList.add("field-bad");
    if (!ok) { mood("nope", 1400); say(fieldsOk ? "Tick the box and we're good to go." : "Almost! Check the highlighted fields."); return; }
    submit("register", {
      name: $("#r-name").value.trim(), phone: normalisePhone($("#r-phone").value), email: $("#r-email").value.trim(),
      password: $("#r-pass").value, referral_code: $("#r-ref").value.trim() || null,
    }, $("#r-submit"));
  };

  setMode(mode, false);
  addEventListener("resize", fitHeight);
  return () => { removeEventListener("resize", fitHeight); clearTimeout(lineTimer); clearTimeout(moodTimer); };
}

// ---------- fleet ----------
async function fleetView(params) {
  let tier = params.get("tier") || "";
  const carry = new URLSearchParams([...params].filter(([k]) => ["mode", "pickup", "dropoff"].includes(k))).toString();
  render(`
    <div class="fleet-head">
      <div><h1 style="font-size:clamp(1.8rem,4vw,2.8rem)">Pick your ride</h1>
        <p class="muted">${carry ? "Your route is saved. Choose a vehicle to see the exact price." : "From bikes for dispatch to trucks for haulage."}</p></div>
      <input id="q" type="search" placeholder="Search brand, model or ID" aria-label="Search vehicles">
    </div>
    <div class="tier-dial" role="group" aria-label="Vehicle class">
      <button data-tier="" aria-pressed="${!tier}">All</button>
      ${state.meta.tiers.map((t) => `<button data-tier="${t.key}" aria-pressed="${tier === t.key}">${esc(t.label)}</button>`).join("")}
      <button data-tier="ev" aria-pressed="false">Electric</button>
    </div>
    <div class="fleet-grid" id="grid">${'<div class="skeleton"></div>'.repeat(6)}</div>`);

  let all = [];
  try { all = await api("/api/fleet"); } catch (e) { toast(e.message, "error"); }

  function show() {
    const q = $("#q").value.trim().toLowerCase();
    let list = all.filter((v) => !tier || (tier === "ev" ? v.is_electric : v.tier === tier));
    if (q) list = list.filter((v) => [v.brand, v.model, v.id, v.tier_label].some((s) => s.toLowerCase().includes(q)));
    const grid = $("#grid");
    if (!list.length) { grid.innerHTML = `<div class="empty"><p>No vehicles match that search. Try another class or clear the search.</p></div>`; return; }
    grid.innerHTML = list.map((v) => `
      <button class="car ${["unavailable", "maintenance"].includes(v.status) ? "off" : ""}" data-id="${esc(v.id)}" aria-label="${esc(v.brand)} ${esc(v.model)}, ${naira(v.daily_rate)} per day">
        <div class="art">${vehiclePhoto(v)}</div>
        <div class="tags"><span class="tag">${esc(v.tier_label)}</span>${v.is_electric ? `<span class="tag ev">Electric</span>` : ""}${v.status !== "available" ? `<span class="tag busy">${v.status === "rented" ? "On a trip now" : v.status === "maintenance" ? "In the workshop" : "Unavailable"}</span>` : ""}</div>
        <h3>${esc(v.brand)} ${esc(v.model)}</h3>
        <div class="meta">${v.year} · ${v.seats} seats · ${esc(v.color)} · ${esc(v.home_zone)}</div>
        <div class="price"><span class="money">${naira(v.daily_rate)}<small class="muted"> a day</small></span>
          <span class="muted" style="font-size:.85rem">or ${naira(v.hourly_route_rate)} an hour on a route</span></div>
      </button>`).join("");
    $$(".car", grid).forEach((card) => {
      const v = list.find((x) => x.id === card.dataset.id);
      card.onclick = () => {
        if (v && ["unavailable", "maintenance"].includes(v.status)) { toast(`${v.brand} ${v.model} can't be booked right now. Try another ${v.tier_label.toLowerCase()}.`); return; }
        location.hash = `#/book/${card.dataset.id}${carry ? "?" + carry : ""}`;
      };
      card.onmousemove = (e) => {
        if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(700px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg) translateY(-3px)`;
      };
      card.onmouseleave = () => (card.style.transform = "");
    });
  }
  $$(".tier-dial button").forEach((b) => b.onclick = () => {
    tier = b.dataset.tier;
    $$(".tier-dial button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    show();
  });
  $("#q").oninput = show;
  show();
}

// ---------- router ----------
let cleanup = null;

async function route() {
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  const [rawPath, query = ""] = location.hash.slice(1).split("?");
  const path = rawPath || "/";
  const params = new URLSearchParams(query);
  renderNav(path);
  const parts = path.split("/").filter(Boolean);

  const go = async () => {
    switch (parts[0]) {
      case undefined: return homeView();
      case "login": return authView("login");
      case "signup": return authView("register");
      case "logout": session.clear(); toast("You're logged out."); location.hash = "#/"; return;
      case "fleet": return fleetView(params);
      case "book": return requireLogin() && bookView(parts[1], params);
      case "pay": return requireLogin() && (parts[1] === "return" ? payReturnView(params) : payView(parts[1]));
      case "success": return requireLogin() && successView(parts[1]);
      case "trips": return requireLogin() && (parts[1] ? tripView(parts[1]) : tripsView());
      case "profile": return requireLogin() && profileView();
      case "admin":
        if (!requireLogin()) return;
        if (!session.isAdmin) { render(`<div class="empty"><h2>Admins only</h2><p>The control room is for fleet staff.</p><a class="btn" href="#/">Go home</a></div>`); return; }
        return adminView(parts[1] || "ops");
      default: render(`<div class="empty"><h2>Wrong turn</h2><p>That page doesn't exist.</p><a class="btn btn-primary" href="#/">Go home</a></div>`);
    }
  };
  const run = async () => { cleanup = await go(); app.focus({ preventScroll: true }); window.scrollTo({ top: 0 }); };
  // No page transition while the login car is on screen: transition snapshots draw above every overlay,
  // so the next page would flash through before the car has driven off.
  const launching = document.body.classList.contains("launching");
  if (document.startViewTransition && !launching && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const vt = document.startViewTransition(run);
    // a newer navigation can skip this transition; that's expected, not an error
    [vt.ready, vt.finished, vt.updateCallbackDone].forEach((pr) => pr?.catch?.(() => {}));
  } else await run();
}

async function boot() {
  // Paystack sends customers back to /paystack/return?reference=...
  if (location.pathname === "/paystack/return") {
    const ref = new URLSearchParams(location.search).get("reference") || "";
    history.replaceState(null, "", `/#/pay/return?reference=${encodeURIComponent(ref)}`);
  }
  if (!document.startViewTransition) document.documentElement.classList.add("no-vt");
  initShell({ toast });
  document.getElementById("theme-btn").onclick = () => {
    const next = document.documentElement.dataset.theme === "day" ? "" : "day";
    if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
    try { localStorage.setItem("oy-theme", next); } catch {}
    window.dispatchEvent(new Event("themechange"));
  };
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    render(`<div class="empty"><h2>Can't reach Oyibo Rentals</h2><p>${esc(e.message)}</p><button class="btn btn-primary" onclick="location.reload()">Try again</button></div>`);
    return;
  }
  syncMe();
  window.addEventListener("hashchange", route);
  route();
}

boot();
