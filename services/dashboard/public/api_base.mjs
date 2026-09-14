/**
 * API-origin allowlist helpers (unit-tested). Never take values from the DOM.
 */

export const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Literal origins permitted for operator fetch(). Semgrep/Codacy SSRF rules
 * only clear when the request URL is selected from a frozen allowlist.
 */
export const ALLOWED_API_ORIGINS = Object.freeze([
  "http://localhost:8010",
  "http://127.0.0.1:8010",
  "https://api.ibexharness.com",
  "https://api.staging.ibexharness.com",
]);

/** @deprecated use ALLOWED_API_ORIGINS — kept for existing imports */
export const ALLOWED_LOCAL_BASES = ALLOWED_API_ORIGINS;

export function isLoopbackHost(hostname) {
  return LOOPBACK_HOSTS.has(String(hostname || "").toLowerCase());
}

/** Hosts allowed for operator API origin (local + product domains). */
export function isAllowedApiHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  if (isLoopbackHost(host)) return true;
  return host === "ibexharness.com" || host.endsWith(".ibexharness.com");
}

function parseOriginUrl(raw) {
  const trimmed = String(raw || "").trim().replace(/\/$/, "");
  if (!trimmed) return null;
  try {
    return new URL(trimmed);
  } catch {
    return null;
  }
}

function hasUserInfo(url) {
  return Boolean(url.username || url.password);
}

function protocolOk(url) {
  if (url.protocol === "https:") return true;
  if (url.protocol === "http:") return isLoopbackHost(url.hostname);
  return false;
}

/**
 * Normalize and allowlist an API origin. Returns null when invalid.
 * HTTP only for loopback; HTTPS required for all other hosts.
 */
export function resolveApiBase(raw) {
  const url = parseOriginUrl(raw);
  if (!url) return null;
  if (hasUserInfo(url)) return null;
  if (!isAllowedApiHost(url.hostname)) return null;
  if (!protocolOk(url)) return null;
  return `${url.protocol}//${url.host}`;
}

/**
 * Pick an origin that is an exact member of ALLOWED_API_ORIGINS (SSRF-safe).
 * Unknown inject values fall back to the local default.
 */
export function pickApiBase(injectedRaw) {
  const resolved = resolveApiBase(injectedRaw);
  const matched = ALLOWED_API_ORIGINS.find((origin) => origin === resolved);
  return matched ?? ALLOWED_API_ORIGINS[0];
}

/** Build frozen endpoint URLs for a previously allowlisted origin. */
export function buildEndpointUrls(origin) {
  const base = ALLOWED_API_ORIGINS.find((o) => o === origin) ?? ALLOWED_API_ORIGINS[0];
  return Object.freeze({
    login: `${base}/v1/operator/session/login`,
    me: `${base}/v1/operator/session/me`,
    logout: `${base}/v1/operator/session/logout`,
    stream: `${base}/v1/operator/events/stream`,
  });
}
