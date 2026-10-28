// The app shell: a collapsible left sidebar (an off-canvas drawer on phones), the notification bell,
// and the sound and theme switches. Pages render into <main>; the shell stays put between pages.
import { api, session } from "./api.js";
import { sound } from "./sound.js";

const ICONS = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  fleet: '<path d="M3 15l2-6c.4-1 1.2-1.6 2.3-1.6h9.4c1.1 0 1.9.6 2.3 1.6l2 6"/><rect x="2" y="15" width="20" height="4" rx="1.5"/><circle cx="7" cy="19.5" r="1.6"/><circle cx="17" cy="19.5" r="1.6"/>',
  trips: '<path d="M4 19c4-1 3-6 8-7s4-6 8-7"/><circle cx="4" cy="19" r="2"/><circle cx="20" cy="5" r="2"/>',
  profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  gps: '<circle cx="12" cy="11" r="3"/><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/>',
  chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3 17.8V21h3.2l6.3-6.3a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/>',
  card: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16c.7-1.4 1.8-2 3-2s2.3.6 3 2"/><path d="M14 10h4M14 13h3"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c1-3.5 3.6-5.5 6.5-5.5s5.5 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.8.8 3 2.6 3.5 5.2"/>',
  login: '<path d="M10 17l5-5-5-5"/><path d="M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/>',
  logout: '<path d="M14 17l5-5-5-5"/><path d="M19 12H7"/><path d="M10 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
  plus: '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
};
export const icon = (name, size = 20) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };
const mobile = () => matchMedia("(max-width: 900px)").matches;

function links(u) {
  if (!u) return [
    { items: [["#/", "Home", "home"], ["#/fleet", "Fleet", "fleet"]] },
    { items: [["#/login", "Log in", "login"], ["#/signup", "Create account", "plus", "cta"]] },
  ];
  const main = { items: [["#/", "Home", "home"], ["#/fleet", "Fleet", "fleet"], ["#/trips", "My trips", "trips"], ["#/profile", "Profile", "profile"]] };
  if (u.role !== "admin") return [main, { items: [["#/logout", "Log out", "logout"]] }];
  main.items = main.items.filter(([href]) => href !== "#/trips");   // staff don't rent, so no "My trips"
  return [main, {
    title: "Control room", items: [["#/admin/ops", "Live GPS", "gps"], ["#/admin/analytics", "Analytics", "chart"], ["#/admin/fleet", "Fleet admin", "wrench"],
      ["#/admin/licences", "Licences", "card", "", "licences"], ["#/admin/claims", "Claims", "shield"], ["#/admin/people", "Customers", "users"]],
  }, { items: [["#/logout", "Log out", "logout"]] }];
}

let badges = {};

export function renderNav(path) {
  const u = session.user;
  const isActive = (href) => {
    const p = href.slice(1);
    if (p === "/") return path === "/";
    if (p === "/admin/ops") return path === "/admin" || path.startsWith("/admin/ops");
    return path === p || path.startsWith(p + "/");
  };
  const nav = document.getElementById("nav");
  nav.innerHTML = `<span class="nav-glow" aria-hidden="true"></span>` + links(u).map((g) => `
    <div class="nav-group">${g.title ? `<p class="nav-title"><span>${g.title}</span></p>` : ""}
      ${g.items.map(([href, label, ic, cls = "", badge = ""]) => `
        <a href="${href}" class="nav-link ${cls} ${isActive(href) ? "active" : ""}" ${isActive(href) ? 'aria-current="page"' : ""} title="${label}" data-badge-key="${badge}">
          <span class="nav-ico">${icon(ic)}</span><span class="nav-label">${label}</span>
          ${badge && badges[badge] ? `<em class="nav-badge">${badges[badge]}</em>` : ""}
        </a>`).join("")}
    </div>`).join("");
  requestAnimationFrame(moveGlow);
  refreshUserBadge();
  document.getElementById("bell").hidden = !u || u.role === "admin";
  document.getElementById("m-bell").hidden = !u || u.role === "admin";
  closeDrawer();
}

function moveGlow() {
  const nav = document.getElementById("nav"), glow = nav?.querySelector(".nav-glow"), a = nav?.querySelector(".nav-link.active");
  if (!glow) return;
  if (!a) { glow.style.opacity = 0; return; }
  glow.style.opacity = 1;
  glow.style.transform = `translateY(${a.offsetTop}px)`;
  glow.style.height = `${a.offsetHeight}px`;
}

export function refreshUserBadge() {
  const pill = document.getElementById("points"), u = session.user;
  if (u && u.role !== "admin") { pill.hidden = false; pill.innerHTML = `<b>${u.loyalty_points.toLocaleString()}</b><span class="nav-label"> Oyibo points</span>`; }
  else pill.hidden = true;
}

export function setBadge(key, count) {
  badges[key] = count;
  const a = document.querySelector(`[data-badge-key="${key}"]`);
  if (!a) return;
  a.querySelector(".nav-badge")?.remove();
  if (count) a.insertAdjacentHTML("beforeend", `<em class="nav-badge">${count}</em>`);
}

// ---------- collapse and drawer ----------
function setCollapsed(on) {
  document.body.classList.toggle("side-collapsed", on);
  store.set("oy-side", on ? "collapsed" : "open");
  document.getElementById("collapse").setAttribute("aria-label", on ? "Expand the menu" : "Collapse the menu");
  document.getElementById("collapse").setAttribute("aria-expanded", String(!on));
  setTimeout(moveGlow, 320);
}
function openDrawer() { document.body.classList.add("drawer-open"); document.getElementById("scrim").hidden = false; document.getElementById("menu-btn").setAttribute("aria-expanded", "true"); }
function closeDrawer() { document.body.classList.remove("drawer-open"); const s = document.getElementById("scrim"); if (s) s.hidden = true; document.getElementById("menu-btn")?.setAttribute("aria-expanded", "false"); }

// ---------- notifications ----------
let seen = null, pollTimer = 0, toastFn = () => {};

async function pollNotifications(showToasts = true) {
  const u = session.user;
  if (!u) return;
  if (u.role === "admin") {   // admins see how many licences wait for review
    try { const rows = await api("/api/admin/licences"); setBadge("licences", rows.filter((l) => l.status === "submitted").length); } catch {}
    return;
  }
  let data;
  try { data = await api("/api/me/notifications"); } catch { return; }
  for (const id of ["bell", "m-bell"]) {
    const b = document.getElementById(id);
    b.querySelector(".bell-dot")?.remove();
    if (data.unread) b.insertAdjacentHTML("beforeend", `<em class="bell-dot">${data.unread > 9 ? "9+" : data.unread}</em>`);
  }
  const fresh = data.items.filter((n) => !n.read && seen !== null && n.id > seen);
  if (showToasts) fresh.slice(0, 2).reverse().forEach((n) => {
    toastFn(`${n.title}. ${n.body}`, n.kind === "speeding" ? "error" : "ok");
    if (n.kind === "speeding") sound.alert();
  });
  seen = Math.max(seen ?? 0, ...data.items.map((n) => n.id), 0);
  const panel = document.getElementById("notif-panel");
  if (!panel.hidden) drawPanel(data);
  window.dispatchEvent(new CustomEvent("notifications", { detail: data }));
}

function drawPanel(data) {
  const panel = document.getElementById("notif-panel");
  const when = (iso) => new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", dateStyle: "medium", timeStyle: "short" });
  panel.innerHTML = `
    <div class="np-head"><h3>Notifications</h3>${data.unread ? `<button class="linkish" id="np-read">Mark all read</button>` : ""}<button type="button" class="x-btn" id="np-close" aria-label="Close notifications">×</button></div>
    <div class="np-list">${data.items.map((n) => `
      <a class="np-item ${n.read ? "" : "unread"} k-${esc(n.kind)}" href="${n.rental ? `#/trips/${esc(n.rental)}` : "#/profile"}">
        <b>${esc(n.title)}</b><span>${esc(n.body)}</span><time>${when(n.created_at)}</time></a>`).join("")
      || `<p class="muted np-empty">Nothing yet. Speeding warnings, licence reviews and messages from our team show up here.</p>`}</div>`;
  panel.querySelector("#np-read")?.addEventListener("click", async () => { await api("/api/me/notifications/read", { method: "POST", body: {} }); pollNotifications(false); });
  panel.querySelector("#np-close").addEventListener("click", (e) => { e.stopPropagation(); toggleBell(false); });
  panel.querySelectorAll(".np-item").forEach((a) => a.addEventListener("click", () => toggleBell(false)));
}

async function toggleBell(open, anchor) {
  const panel = document.getElementById("notif-panel");
  open = open ?? panel.hidden;
  panel.hidden = !open;
  if (!open) return;
  const r = anchor.getBoundingClientRect();
  const side = document.getElementById("sidebar").getBoundingClientRect();   // open beside the sidebar, not over it
  panel.style.left = mobile() ? "12px" : `${Math.min(side.right + 12, innerWidth - 380)}px`;
  panel.style.top = mobile() ? `${r.bottom + 10}px` : `${Math.max(12, r.bottom - 420)}px`;
  panel.innerHTML = `<p class="muted np-empty">Loading…</p>`;
  try { drawPanel(await api("/api/me/notifications")); } catch {}
}

export function initShell({ toast }) {
  toastFn = toast;
  const saved = store.get("oy-side");
  if (saved === "collapsed" && !mobile()) document.body.classList.add("side-collapsed");
  document.getElementById("collapse").onclick = () => setCollapsed(!document.body.classList.contains("side-collapsed"));
  document.getElementById("menu-btn").onclick = () => (document.body.classList.contains("drawer-open") ? closeDrawer() : openDrawer());
  document.getElementById("scrim").onclick = closeDrawer;
  addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); toggleBell(false); } });
  addEventListener("resize", () => requestAnimationFrame(moveGlow));
  for (const id of ["bell", "m-bell"]) {
    const b = document.getElementById(id);
    b.onclick = (e) => { e.stopPropagation(); toggleBell(undefined, b); };
  }
  document.addEventListener("click", (e) => { const p = document.getElementById("notif-panel"); if (!p.hidden && !p.contains(e.target)) toggleBell(false); });

  // sound switch
  const sb = document.getElementById("sound-btn");
  const paint = () => { sb.setAttribute("aria-pressed", String(sound.enabled)); sb.title = sound.enabled ? "Sound on" : "Sound off"; sb.classList.toggle("off", !sound.enabled); };
  sb.onclick = () => { sound.toggle(); paint(); if (sound.enabled) sound.blip(); };
  paint();

  clearInterval(pollTimer);
  pollTimer = setInterval(() => pollNotifications(true), 12000);
  pollNotifications(false);
  window.addEventListener("login", () => { seen = null; pollNotifications(false); });
}

export const refreshNotifications = () => pollNotifications(false);
