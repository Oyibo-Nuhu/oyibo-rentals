import { sound } from "./sound.js";

// The Oyibo mascot: a side-on coupe whose headlight is an eye.
// Used on the auth screen (idle, blinking, shutting its eye while you type a password)
// and in the launch sequence that plays after every login and sign-up.

let uid = 0;

// "Zuma" (after Zuma Rock): an original glossy EV coupe with studio lighting —
// layered paint gradients, specular highlights, a lilac rim light and a floor reflection.
export function mascotCar() {
  const id = `m${++uid}`;
  const u = (n) => `url(#${id}-${n})`;
  return `
  <svg class="mascot-svg" viewBox="0 0 340 168" role="img" aria-label="Zuma, the Oyibo Rentals mascot car">
    <defs>
      <linearGradient id="${id}-paint" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#FFB3C8"/><stop offset=".18" stop-color="#FF6A92"/>
        <stop offset=".5" stop-color="#FF2E63"/><stop offset=".78" stop-color="#B0103F"/><stop offset="1" stop-color="#5A0622"/>
      </linearGradient>
      <linearGradient id="${id}-sheen" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".35" stop-color="#fff" stop-opacity=".55"/>
        <stop offset=".6" stop-color="#fff" stop-opacity=".15"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="${id}-glass" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#6E4C9C"/><stop offset=".45" stop-color="#2A1636"/><stop offset="1" stop-color="#0C0610"/>
      </linearGradient>
      <radialGradient id="${id}-rim" cx=".4" cy=".35" r=".75">
        <stop offset="0" stop-color="#FFFFFF"/><stop offset=".45" stop-color="#CDBFD0"/><stop offset="1" stop-color="#5B4A57"/>
      </radialGradient>
      <radialGradient id="${id}-tyre" cx=".45" cy=".4" r=".7">
        <stop offset=".6" stop-color="#2A1E26"/><stop offset="1" stop-color="#0A0609"/>
      </radialGradient>
      <radialGradient id="${id}-sclera" cx=".45" cy=".4" r=".7">
        <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#E3D8F5"/>
      </radialGradient>
      <radialGradient id="${id}-iris" cx=".4" cy=".35" r=".7">
        <stop offset="0" stop-color="#E6DCFF"/><stop offset=".55" stop-color="#9B7BFF"/><stop offset="1" stop-color="#4B2BB0"/>
      </radialGradient>
      <linearGradient id="${id}-beam" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#E6DCFF" stop-opacity=".9"/><stop offset="1" stop-color="#B79CFF" stop-opacity="0"/>
      </linearGradient>
      <radialGradient id="${id}-floor" cx=".5" cy=".5" r=".5">
        <stop offset="0" stop-color="#FF2E63" stop-opacity=".45"/><stop offset="1" stop-color="#FF2E63" stop-opacity="0"/>
      </radialGradient>
      <clipPath id="${id}-eye"><path d="M280 84 C290 66 316 64 328 79 C320 95 294 98 280 84 Z"/></clipPath>
      <clipPath id="${id}-bodyclip"><path id="${id}-shape" d="${BODY}"/></clipPath>
      <filter id="${id}-soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.4"/></filter>
      <filter id="${id}-glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="4"/></filter>
    </defs>

    <ellipse cx="172" cy="150" rx="170" ry="16" fill="${u("floor")}"/>
    <ellipse class="m-shadow" cx="174" cy="146" rx="148" ry="7" filter="${u("soft")}"/>
    <polygon class="m-beam" points="326,80 480,46 480,122" fill="${u("beam")}"/>

    <g class="m-body">
      <g class="m-puffs" aria-hidden="true">
        <circle cx="14" cy="114" r="7"/><circle cx="2" cy="108" r="9"/><circle cx="-12" cy="101" r="11"/>
      </g>
      <path d="${BODY}" fill="${u("paint")}"/>
      <g clip-path="${u("bodyclip")}">
        <!-- rim light from below, lilac -->
        <path d="M20 122 Q170 108 334 122" stroke="#B79CFF" stroke-width="7" fill="none" opacity=".7" filter="${u("soft")}"/>
        <!-- long specular sheen across the shoulder line -->
        <path d="M30 88 C90 74 200 70 320 84 L320 92 C200 80 90 84 30 96 Z" fill="${u("sheen")}" filter="${u("soft")}"/>
        <!-- hotspots -->
        <ellipse cx="62" cy="86" rx="20" ry="5" fill="#fff" opacity=".55" filter="${u("soft")}" transform="rotate(-12 62 86)"/>
        <ellipse cx="290" cy="70" rx="16" ry="4" fill="#fff" opacity=".6" filter="${u("soft")}" transform="rotate(14 290 70)"/>
        <!-- door seam and sill -->
        <path d="M186 74 Q182 98 186 118" stroke="#5A0622" stroke-opacity=".35" stroke-width="1.5" fill="none"/>
        <path d="M120 112 L228 112" stroke="#fff" stroke-opacity=".18" stroke-width="2"/>
      </g>
      <!-- greenhouse: one sweep of glass with a thin pillar -->
      <path d="M104 72 C120 52 144 42 172 41 C198 40 218 46 236 62 L238 68 Q170 66 104 72 Z" fill="${u("glass")}"/>
      <path d="M180 41.5 L178 67" stroke="#2A0E1A" stroke-width="5"/>
      <path d="M126 64 L146 46 M136 66 L156 46" stroke="#fff" stroke-opacity=".28" stroke-width="4" stroke-linecap="round"/>
      <path d="M104 72 C120 52 144 42 172 41 C198 40 218 46 236 62" stroke="#F4ECF1" stroke-opacity=".7" stroke-width="2" fill="none"/>
      <!-- wraparound LED tail light -->
      <rect class="m-tail-glow" x="13" y="86" width="22" height="14" rx="7" filter="${u("glow")}"/>
      <rect class="m-tail" x="16" y="89" width="16" height="7" rx="3.5"/>

      <g class="m-eye">
        <path d="M280 84 C290 66 316 64 328 79 C320 95 294 98 280 84 Z" fill="${u("sclera")}"/>
        <g clip-path="${u("eye")}">
          <g class="m-pupil">
            <circle cx="308" cy="81" r="8.5" fill="${u("iris")}"/>
            <circle cx="308.5" cy="81.5" r="4" fill="#160A1A"/>
            <circle cx="311" cy="78" r="2.2" fill="#fff"/><circle cx="305" cy="85" r="1" fill="#fff" opacity=".8"/>
          </g>
          <rect class="m-lid" x="276" y="62" width="56" height="38" fill="#D21A50"/>
        </g>
        <path d="M280 84 C290 66 316 64 328 79" stroke="#5A0622" stroke-width="2" fill="none" opacity=".6"/>
        <path class="m-brow" d="M284 70 Q302 58 322 66" stroke="#2A0E1A" stroke-width="3.5" fill="none" stroke-linecap="round"/>
      </g>
      <path class="m-sparkle" d="M338 56 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" fill="#E6DCFF"/>
      <path d="M314 106 Q326 106 331 100" stroke="#2A0E1A" stroke-width="2.5" fill="none" stroke-linecap="round" opacity=".5"/>

      ${wheel(86, id)}${wheel(262, id)}
    </g>
  </svg>`;
}

const BODY = "M26 122 C18 122 15 115 16 106 C17 94 24 86 42 82 C62 77 82 74 98 72 C116 50 140 37 172 36 C206 35 228 42 248 60 C266 64 292 67 308 73 C324 79 332 91 332 104 C332 115 328 122 318 122 L294 122 A32 32 0 0 0 230 122 L118 122 A32 32 0 0 0 54 122 Z";

const wheel = (x, id) => `
  <g class="m-wheel" style="transform-origin:${x}px 122px">
    <circle cx="${x}" cy="122" r="25" fill="url(#${id}-tyre)"/>
    <circle cx="${x}" cy="122" r="16.5" fill="url(#${id}-rim)"/>
    ${[0, 72, 144, 216, 288].map((a) => `<path d="M${x - 2.6} 122 L${x - 1.6} 107.5 L${x + 1.6} 107.5 L${x + 2.6} 122 Z" fill="#3A2A35" transform="rotate(${a} ${x} 122)"/>`).join("")}
    <circle cx="${x}" cy="122" r="5" fill="#FF2E63"/><circle cx="${x - 1.4}" cy="120.6" r="1.6" fill="#fff" opacity=".8"/>
    <path d="M${x - 19} ${122 - 12} A22 22 0 0 1 ${x + 6} ${122 - 21}" stroke="#fff" stroke-opacity=".22" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  </g>`;

/**
 * Plays the wink → rev → zoom-off sequence over the whole screen.
 * `onReveal` runs while the car is leaving, so the next page renders behind the overlay.
 * Resolves when the overlay is gone. Click, tap or Esc skips it.
 */
export function launchSequence({ name = "", mode = "login", onReveal = () => {} } = {}) {
  const first = (name || "").trim().split(/\s+/)[0] || "driver";
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const el = document.createElement("div");
  el.className = `launch${reduce ? " reduced" : ""}`;
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "assertive");
  el.innerHTML = `
    <div class="launch-lines" aria-hidden="true">${"<i></i>".repeat(9)}</div>
    <div class="launch-road" aria-hidden="true"></div>
    <div class="launch-car" aria-hidden="true">
      <i class="trail t1"></i><i class="trail t2"></i>
      ${mascotCar()}
    </div>
    <div class="launch-msg">
      <span class="launch-eyebrow">${mode === "register" ? "Keys handed over" : "Engine on"}</span>
      <h2>${mode === "register" ? "You're in" : "Welcome back"}, <span>${escapeHtml(first)}</span></h2>
    </div>
    <button class="launch-skip" type="button">Skip</button>`;
  document.body.append(el);
  document.body.classList.add("launching");
  if (!reduce) sound.vroom(0.05);   // idle as Zuma rolls in, a rev, then the roar as it zooms off

  return new Promise((resolve) => {
    let revealed = false, done = false;
    const timers = [];
    const reveal = () => { if (!revealed) { revealed = true; try { onReveal(); } catch (e) { console.error(e); } } };
    const finish = () => {
      if (done) return;
      done = true;
      timers.forEach(clearTimeout);
      reveal();
      el.classList.add("out");
      setTimeout(() => { el.remove(); document.body.classList.remove("launching"); resolve(); }, reduce ? 150 : 420);
      removeEventListener("keydown", onKey);
    };
    const onKey = (e) => { if (e.key === "Escape" || e.key === "Enter") finish(); };
    el.addEventListener("click", finish);
    addEventListener("keydown", onKey);

    if (reduce) {
      timers.push(setTimeout(reveal, 300), setTimeout(finish, 1100));
    } else {
      timers.push(setTimeout(reveal, 2600), setTimeout(finish, 3050));   // page swaps under the overlay once the car is gone
    }
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
