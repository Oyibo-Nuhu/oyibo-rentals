// The customer's own page: details, driver's licence, speeding record, password, notifications.
import { api, naira, session } from "./api.js";
import { $, $$, esc, fmtDate, render, toast } from "./app.js";
import { refreshUserBadge } from "./shell.js";

const STATES = ["Lagos", "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River", "Delta",
  "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT Abuja", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara",
  "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara"];

const LIC_STATUS = {
  verified: ["Verified", "ok", "You can drive yourself on any booking."],
  submitted: ["Under review", "wait", "You can already book self-drive. Our team will check the photo shortly."],
  rejected: ["Not accepted", "bad", ""],
  expired: ["Expired", "bad", "Upload your renewed licence to drive yourself again."],
  missing: ["Not added", "none", "Add your licence to drive yourself, or choose a driver when you book."],
};

function plateFor(name, phone) {
  const letters = (name.trim().split(/\s+/)[0] || "").replace(/[^a-z]/gi, "").toUpperCase().padEnd(3, "X").slice(0, 3);
  return `${letters}-${(phone.replace(/\D/g, "").slice(-3) || "").padStart(3, "0")}-OY`;
}

export async function profileView() {
  let p;
  try { p = await api("/api/me"); } catch (e) { render(`<div class="empty"><p>${esc(e.message)}</p></div>`); return; }
  const u = p.user, admin = u.role === "admin", s = p.stats, pol = p.speeding_policy;
  const initials = u.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const licKey = p.self_drive.status === "expired" ? "expired" : p.licence ? p.licence.status : "missing";
  const [licLabel, licTone, licText] = LIC_STATUS[licKey] || LIC_STATUS.missing;

  render(`
    <section class="pf-hero">
      <div class="pf-avatar" aria-hidden="true">${esc(initials)}</div>
      <div class="pf-id">
        <h1>${esc(u.name)}</h1>
        <p class="muted">${esc(u.email)} · Member since ${fmtDate(p.member_since, { dateStyle: "long" })}</p>
      </div>
      ${admin ? "" : `<div class="plate pf-plate" aria-label="Your Oyibo plate"><small>LAGOS · OYIBO</small><strong>${esc(plateFor(u.name, u.phone))}</strong></div>`}
    </section>

    ${admin ? "" : `
    <section class="pf-stats">
      <div><span>Trips</span><b data-count="${s.trips}">0</b></div>
      <div><span>Distance</span><b data-count="${s.km}" data-suffix=" km">0</b></div>
      <div><span>Spent</span><b data-count="${s.spent}" data-money="1">₦0</b></div>
      <div><span>Oyibo points</span><b data-count="${u.loyalty_points}">0</b></div>
      <div><span>Speeding incidents</span><b data-count="${s.speeding_incidents}">0</b><small>${s.speeding_charges ? `${naira(s.speeding_charges)} in charges` : "No charges"}</small></div>
    </section>`}

    <div class="pf-grid">
      <div class="pf-col">
        ${admin ? "" : `
        <section class="panel pf-card" id="lic-card">
          <div class="box-head"><h2>Driver's licence</h2><span class="lic-pill ${licTone}">${licLabel}</span></div>
          <p class="muted">${esc(licKey === "rejected" ? p.self_drive.reason : licText)}</p>
          ${p.licence ? `<dl class="pf-dl"><dt>Number</dt><dd>${esc(p.licence.number)}</dd><dt>State</dt><dd>${esc(p.licence.state || "–")}</dd>
            <dt>Expires</dt><dd>${fmtDate(p.licence.expires_on + "T00:00:00", { dateStyle: "medium" })}</dd></dl>` : ""}
          <button class="btn ${p.licence ? "btn-ghost" : "btn-primary"} btn-sm" id="lic-open" aria-expanded="false" aria-controls="lic-form">${p.licence ? "Upload a new licence" : "Add my licence"}</button>
          <form id="lic-form" class="lic-form" hidden novalidate>
            <div class="field"><label>Type of licence</label>
              <div class="seg" role="group" aria-label="Type of licence">
                <button type="button" data-kind="full" aria-pressed="true">Full driver's licence</button>
                <button type="button" data-kind="learner" aria-pressed="false">Learner's permit</button>
              </div>
              <div class="lic-warn" id="lic-learner" hidden>Learner's permits aren't accepted for self-drive. You can still rent anything: just add one of our professional drivers when you book.</div>
            </div>
            <div class="row">
              <div class="field"><label for="lic-num">Licence number</label><input id="lic-num" placeholder="e.g. LAG12345AA01" autocapitalize="characters" required><div class="hint">As printed on the card.</div></div>
              <div class="field"><label for="lic-exp">Expiry date</label><input id="lic-exp" type="date" required></div>
            </div>
            <div class="field"><label for="lic-state">State of issue</label><select id="lic-state">${STATES.map((st) => `<option>${st}</option>`).join("")}</select></div>
            <label class="photo-drop" id="lic-drop" for="lic-file">
              <input type="file" id="lic-file" accept="image/jpeg,image/png,image/webp" hidden>
              <span id="lic-preview"><b>Photo of the front of your licence</b><small>Clear and readable, JPG, PNG or WebP, up to 6 MB. Only our verification team can see it.</small></span>
            </label>
            <button class="btn btn-primary btn-block" id="lic-submit">Submit licence</button>
          </form>
        </section>

        <section class="panel pf-card">
          <h2>Speed rules</h2>
          <div class="strike-rule">
            ${Array.from({ length: pol.free_strikes }, (_, i) => `<span class="strike warn">Warning ${i + 1}</span>`).join("")}
            <span class="strike fee">${naira(pol.fee)} each after</span>
          </div>
          <p class="muted">Going over ${pol.limit_kmh} km/h counts as one incident, however long it lasts. You get ${pol.free_strikes} warnings per trip by notification; from the ${pol.free_strikes + 1}th, each incident costs ${naira(pol.fee)}, taken from your deposit. Trips with one of our drivers never count against you.</p>
        </section>`}

        <section class="panel pf-card">
          <h2>Notifications</h2>
          <div id="pf-notes"><div class="skeleton" style="height:120px"></div></div>
        </section>
      </div>

      <div class="pf-col">
        <form class="panel pf-card" id="pf-form" novalidate>
          <h2>Your details</h2>
          <div class="field"><label for="pf-name">Full name</label><input id="pf-name" value="${esc(u.name)}" autocomplete="name"></div>
          <div class="field"><label for="pf-phone">Phone number</label><input id="pf-phone" value="${esc(u.phone)}" inputmode="tel" autocomplete="tel"></div>
          <div class="field"><label for="pf-email">Email</label><input id="pf-email" value="${esc(u.email)}" disabled><div class="hint">Contact us to change the email on your account.</div></div>
          <button class="btn btn-primary" id="pf-save">Save changes</button>
        </form>

        ${admin ? "" : `
        <section class="panel pf-card">
          <h2>Invite friends</h2>
          <p class="muted">You both get 500 Oyibo points when a friend signs up with your code.</p>
          <div class="ref-row"><code class="ref-code">${esc(u.referral_code)}</code><button class="btn btn-ghost btn-sm" id="ref-copy">Copy code</button></div>
        </section>`}

        <form class="panel pf-card" id="pw-form" novalidate>
          <h2>Change password</h2>
          <div class="field"><label for="pw-cur">Current password</label><input id="pw-cur" type="password" autocomplete="current-password"></div>
          <div class="field"><label for="pw-new">New password</label><input id="pw-new" type="password" autocomplete="new-password" minlength="8"><div class="hint">At least 8 characters.</div></div>
          <button class="btn btn-ghost" id="pw-save">Change password</button>
        </form>
      </div>
    </div>`);

  // numbers roll up
  $$("[data-count]").forEach((el) => {
    const to = Number(el.dataset.count), money = el.dataset.money, suf = el.dataset.suffix || "", t0 = performance.now();
    const fmt = (v) => (money ? naira(v) : (Number.isInteger(to) ? Math.round(v).toLocaleString() : v.toFixed(1)) + suf);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(to); return; }
    const step = (t) => { const k = Math.min(1, (t - t0) / 900); el.textContent = fmt(to * (1 - Math.pow(1 - k, 3))); if (k < 1 && el.isConnected) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });

  // details
  $("#pf-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const user = await api("/api/me", { method: "PUT", body: { name: $("#pf-name").value, phone: $("#pf-phone").value } });
      session.set({ ...session.get(), user }); refreshUserBadge();
      $(".pf-id h1").textContent = user.name;
      toast("Your details are saved.", "ok");
    } catch (err) { toast(err.message, "error"); }
  };
  $("#pw-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/me/password", { method: "POST", body: { current_password: $("#pw-cur").value, new_password: $("#pw-new").value } });
      $("#pw-form").reset(); toast("Password changed.", "ok");
    } catch (err) { toast(err.message, "error"); }
  };
  $("#ref-copy")?.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(u.referral_code); toast("Referral code copied.", "ok"); } catch { toast(`Your code is ${u.referral_code}.`); }
  });

  // notifications list
  async function notes() {
    let d;
    try { d = await api("/api/me/notifications"); } catch { return; }
    const box = $("#pf-notes"); if (!box) return;
    box.innerHTML = d.items.length ? `
      ${d.unread ? `<button class="linkish" id="pf-read" style="margin-bottom:8px">Mark all read</button>` : ""}
      <div class="pf-notes">${d.items.slice(0, 8).map((n) => `<div class="np-item ${n.read ? "" : "unread"} k-${esc(n.kind)}"><b>${esc(n.title)}</b><span>${esc(n.body)}</span>
        <time>${fmtDate(n.created_at)}${n.rental ? ` · <a href="#/trips/${esc(n.rental)}">${esc(n.rental)}</a>` : ""}</time></div>`).join("")}</div>`
      : `<p class="muted">Nothing yet. Speeding warnings, licence reviews and messages from our team show up here.</p>`;
    $("#pf-read")?.addEventListener("click", async () => { await api("/api/me/notifications/read", { method: "POST", body: {} }); notes(); });
  }
  notes();
  const onNotes = () => notes();
  window.addEventListener("notifications", onNotes);

  if (admin) return () => window.removeEventListener("notifications", onNotes);

  // licence form
  let kind = "full", file = null;
  const form = $("#lic-form");
  const tomorrow = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  $("#lic-exp").min = tomorrow;
  $("#lic-open").onclick = () => { form.hidden = !form.hidden; $("#lic-open").setAttribute("aria-expanded", String(!form.hidden)); if (!form.hidden) $("#lic-num").focus(); };
  $$("[data-kind]", form).forEach((b) => b.onclick = () => {
    kind = b.dataset.kind;
    $$("[data-kind]", form).forEach((x) => x.setAttribute("aria-pressed", x === b));
    $("#lic-learner").hidden = kind !== "learner";
    $("#lic-submit").disabled = kind === "learner";
  });
  const setFile = (f) => {
    if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { toast("Use a JPG, PNG or WebP photo.", "error"); return; }
    if (f.size > 6 * 1024 * 1024) { toast("That photo is over 6 MB.", "error"); return; }
    file = f;
    $("#lic-preview").innerHTML = `<img src="${URL.createObjectURL(f)}" alt="Your licence photo"><small>${esc(f.name)} · click to change</small>`;
  };
  $("#lic-file").onchange = (e) => setFile(e.target.files[0]);
  const drop = $("#lic-drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (kind === "learner") return;
    if (!$("#lic-num").value.trim()) { toast("Enter your licence number.", "error"); return; }
    if (!$("#lic-exp").value) { toast("Enter the expiry date.", "error"); return; }
    if (!file) { toast("Add a photo of your licence.", "error"); return; }
    const fd = new FormData();
    fd.append("kind", kind); fd.append("number", $("#lic-num").value); fd.append("expires_on", $("#lic-exp").value);
    fd.append("state", $("#lic-state").value); fd.append("file", file);
    const btn = $("#lic-submit"); btn.disabled = true; btn.textContent = "Uploading…";
    try {
      await api("/api/me/licence", { method: "POST", form: fd });
      toast("Licence submitted. You can book self-drive now.", "ok");
      const back = sessionStorage.getItem("oy-after-licence");
      if (back) { sessionStorage.removeItem("oy-after-licence"); location.hash = back; } else profileView();
    } catch (err) { toast(err.message, "error"); btn.disabled = false; btn.textContent = "Submit licence"; }
  };
  if (location.hash.includes("licence=1")) { form.hidden = false; $("#lic-open").setAttribute("aria-expanded", "true"); $("#lic-card").scrollIntoView({ behavior: "smooth" }); }
  return () => window.removeEventListener("notifications", onNotes);
}
