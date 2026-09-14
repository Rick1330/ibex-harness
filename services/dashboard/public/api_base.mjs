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

/** Local-dev defaults only — never used as a silent fallback for rejected inject. */
export const LOCAL_DEV_ORIGINS = Object.freeze([
  "http://localhost:8010",
  "http://127.0.0.1:8010",
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
 * Pick an allowlisted API origin.
 * - No inject (local dev): loopback default.
 * - Inject present (deployed shell): must match ALLOWED_API_ORIGINS exactly, else null.
 */
export function pickApiBase(injectedRaw) {
  const trimmed = String(injectedRaw || "").trim();
  if (!trimmed) {
    return LOCAL_DEV_ORIGINS[0];
  }
  const resolved = resolveApiBase(trimmed);
  return ALLOWED_API_ORIGINS.find((origin) => origin === resolved) ?? null;
}

/** Build frozen endpoint URLs for a previously allowlisted origin. */
export function buildEndpointUrls(origin) {
  const base = ALLOWED_API_ORIGINS.find((o) => o === origin);
  if (!base) {
    throw new Error("API origin is not on the allowlist");
  }
  return Object.freeze({
    login: `${base}/v1/operator/session/login`,
    me: `${base}/v1/operator/session/me`,
    logout: `${base}/v1/operator/session/logout`,
    stream: `${base}/v1/operator/events/stream`,
  });
}
