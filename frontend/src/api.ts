/**
 * Every call to the backend goes through here.
 * - VITE_API_URL: backend origin in production (e.g. https://exunu-api.onrender.com). Empty in
 *   development: Vite proxies /api to the local backend (vite.config.ts).
 * - Adds the session token saved at login.
 */

export const API_URL = ((import.meta as any).env?.VITE_API_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "exunu_session_token";

export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage blocked: session lasts until reload */ }
}

export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** fetch() against the backend with the session token. Same signature as fetch. */
const EXPIRES_KEY = "ld_session_expires";

/** When the current login ends (ISO time from the server); the app returns to the login page then. */
export function setSessionExpiry(iso: string | null) {
  try { if (iso) localStorage.setItem(EXPIRES_KEY, iso); else localStorage.removeItem(EXPIRES_KEY); } catch { /* storage blocked */ }
}
export function sessionExpiry(): number | null {
  try { const v = localStorage.getItem(EXPIRES_KEY); return v ? new Date(v).getTime() : null; } catch { return null; }
}

/** The server refused the session (logged out, account disabled): forget it and tell the app. */
export function expireSession() {
  if (!getToken()) return;
  setToken(null);
  setSessionExpiry(null);
  window.dispatchEvent(new Event("ld-session-expired"));
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(apiUrl(path), { ...init, headers }).then(res => {
    // The session ran out on the server: back to the login page (not for the login call itself)
    if (res.status === 401 && token && !path.includes("/auth/login") && !path.includes("/auth/register")) expireSession();
    return res;
  });
}

/** JSON helper: throws with the backend's error message on a non-2xx answer. */
export async function apiJson<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data && (data.detail || data.error || data.message)) || `HTTP ${res.status}`);
  return data as T;
}
