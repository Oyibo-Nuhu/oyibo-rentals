// Generic vehicle silhouettes by tier, tinted with the vehicle's colour.
const COLOURS = {
  white: "#F2F2F5", black: "#2B2B33", silver: "#B9BCC8", grey: "#8A8FA0", gray: "#8A8FA0", red: "#E5484D",
  blue: "#4C7DF0", green: "#3FB878", yellow: "#FFC83D", teal: "#2BB3B1", quartz: "#C9C2B8", emerald: "#1E8C62",
};

function tint(name = "") {
  const n = name.toLowerCase();
  for (const [k, v] of Object.entries(COLOURS)) if (n.includes(k)) return v;
  return "#B79CFF";
}

const wheel = (x, y, r = 11) =>
  `<circle cx="${x}" cy="${y}" r="${r}" fill="#16181d"/><circle cx="${x}" cy="${y}" r="${r * 0.45}" fill="#8a8f9c"/>`;

const SHAPES = {
  luxury: (c) => `<path d="M14 62 Q16 50 36 47 L62 32 Q72 27 96 27 L124 28 Q138 30 150 44 L178 48 Q190 51 190 62 L190 68 L14 68 Z" fill="${c}"/>
    <path d="M68 34 L96 31 L100 46 L60 46 Z M104 31 L124 32 Q134 34 142 45 L106 46 Z" fill="#1a1d24" opacity=".85"/>${wheel(48, 68)}${wheel(158, 68)}`,
  executive: (c) => `<path d="M12 64 L14 48 Q16 42 30 40 L50 24 Q56 20 70 20 L140 20 Q150 20 158 28 L172 40 Q188 42 190 52 L190 68 L12 68 Z" fill="${c}"/>
    <path d="M56 27 L92 25 L94 40 L42 40 Z M100 25 L138 25 Q146 25 152 32 L158 40 L102 40 Z" fill="#1a1d24" opacity=".85"/>${wheel(48, 68, 13)}${wheel(156, 68, 13)}`,
  economy: (c) => `<path d="M16 64 Q18 50 38 47 L64 30 Q72 26 90 26 L118 27 Q130 28 142 42 L170 46 Q186 49 186 62 L186 68 L16 68 Z" fill="${c}"/>
    <path d="M70 32 L92 30 L94 44 L58 44 Z M100 30 L118 31 Q128 33 134 43 L102 44 Z" fill="#1a1d24" opacity=".85"/>${wheel(50, 68)}${wheel(154, 68)}`,
  commercial: (c) => `<path d="M12 68 L12 26 Q12 14 26 14 L150 14 Q166 14 176 30 L188 48 Q190 52 190 58 L190 68 Z" fill="${c}"/>
    <path d="M24 22 h28 v18 h-28z M58 22 h28 v18 h-28z M92 22 h28 v18 h-28z M126 22 h22 v18 h-22z M152 22 Q164 22 172 36 L174 40 h-22z" fill="#1a1d24" opacity=".85"/>${wheel(46, 68, 12)}${wheel(158, 68, 12)}`,
  truck: (c) => `<rect x="8" y="10" width="118" height="50" rx="4" fill="#d9dbea"/><path d="M130 60 L130 22 Q130 16 138 16 L164 16 Q172 16 178 26 L190 44 L190 60 Z" fill="${c}"/>
    <path d="M140 22 h20 Q168 22 172 30 L178 40 h-38z" fill="#1a1d24" opacity=".85"/><rect x="8" y="58" width="182" height="6" fill="#4a4f5c"/>${wheel(34, 68)}${wheel(62, 68)}${wheel(162, 68)}`,
  tricycle: (c) => `<path d="M40 66 L40 30 Q40 16 56 14 L132 14 Q150 14 156 30 L164 54 L176 58 L176 66 Z" fill="${c}"/>
    <path d="M52 22 h44 v26 h-44z M104 22 h26 Q144 22 148 34 L152 48 h-48z" fill="#1a1d24" opacity=".8"/>
    <rect x="34" y="10" width="128" height="7" rx="3" fill="#1a1d24"/>${wheel(66, 68, 12)}${wheel(166, 68, 10)}`,
  bike: (c) => `${wheel(52, 64, 16)}${wheel(150, 64, 16)}<path d="M52 64 L84 36 L124 36 L150 64" stroke="#4a4f5c" stroke-width="5" fill="none"/>
    <path d="M78 36 Q86 22 112 24 L132 30 L120 40 L84 42 Z" fill="${c}"/><path d="M126 30 L138 18 L148 20" stroke="${c}" stroke-width="5" fill="none" stroke-linecap="round"/>`,
};

const SUV_WORDS = ["g 63", "range rover", "lx ", "lx6", "cullinan", "prado", "highlander", "explorer", "rx ", "gle", "atto", "ioniq"];

export function vehicleArt(tier, colour, name = "") {
  const n = (name + " ").toLowerCase();
  let shape = tier;
  if (["luxury", "economy", "executive"].includes(tier)) shape = SUV_WORDS.some((w) => n.includes(w)) ? "executive" : tier === "executive" ? "economy" : tier;
  const draw = SHAPES[shape] || SHAPES.economy;
  return `<svg viewBox="0 0 200 84" role="img" aria-hidden="true">${draw(tint(colour))}</svg>`;
}

const escAttr = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Real photo (freely licensed, from Wikimedia Commons, or uploaded by an admin) with the illustration as fallback.
// `credit`: "short" for a one-line caption without links (safe inside buttons), "link" for a linked credit.
export function vehiclePhoto(v, { credit = "short", eager = false } = {}) {
  const name = `${v.brand} ${v.model}`;
  const fallback = `<div class="photo-fallback">${vehicleArt(v.tier, v.color, name)}</div>`;
  if (!v.photo) return `<figure class="photo no-photo">${fallback}</figure>`;
  const c = v.photo_credit || {};
  const author = c.author && c.author.length > 40 ? c.author.slice(0, 38) + "…" : c.author;
  const caption = !credit ? "" : credit === "link" && c.source
    ? `<figcaption>Photo: <a href="${escAttr(c.source)}" target="_blank" rel="noopener">${escAttr(author)}</a>${c.license ? ` · ${c.license_url ? `<a href="${escAttr(c.license_url)}" target="_blank" rel="noopener">${escAttr(c.license)}</a>` : escAttr(c.license)}` : ""}</figcaption>`
    : `<figcaption>${escAttr(author)}${c.license ? ` · ${escAttr(c.license)}` : ""}</figcaption>`;
  return `<figure class="photo">
    <img src="${escAttr(v.photo)}" alt="${escAttr(name)}" ${eager ? "" : 'loading="lazy"'} decoding="async"
      onerror="this.closest('.photo').classList.add('no-photo')">${fallback}${caption}</figure>`;
}
