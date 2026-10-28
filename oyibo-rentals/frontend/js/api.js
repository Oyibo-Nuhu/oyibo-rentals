// Small API client with the session kept in localStorage.
const KEY = "oy-session";

export const session = {
  get() {
    try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
  },
  set(data) {
    try { localStorage.setItem(KEY, JSON.stringify(data)); } catch {}
  },
  clear() {
    try { localStorage.removeItem(KEY); } catch {}
  },
  get user() { return this.get()?.user || null; },
  get isAdmin() { return this.user?.role === "admin"; },
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = session.get()?.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let res;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && token) {
      session.clear();
      location.hash = "#/login";
    }
    const detail = typeof data === "object" ? data.detail : data;
    throw new ApiError(typeof detail === "string" ? detail : "Something went wrong.", res.status);
  }
  return data;
}

export const naira = (n, d = 0) =>
  "₦" + Number(n || 0).toLocaleString("en-NG", { minimumFractionDigits: d, maximumFractionDigits: d });
