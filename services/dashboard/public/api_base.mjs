/**
 * API-origin allowlist helpers (unit-tested). Never take values from the DOM.
 */

export const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** Known-safe local defaults used when no inject config is present. */
export const ALLOWED_LOCAL_BASES = Object.freeze([
  "http://localhost:8010",
  "http://127.0.0.1:8010",
]);

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

function originAllowed(url) {
  if (url.username || url.password) return false;
  return isAllowedApiHost(url.hostname);
}

function protocolOk(url) {
  const loopback = isLoopbackHost(url.hostname);
  if (url.protocol === "http:") return loopback;
  return url.protocol === "https:";
}

/**
 * Normalize and allowlist an API origin. Returns null when invalid.
 * HTTP only for loopback; HTTPS required for all other hosts.
 */
export function resolveApiBase(raw) {
  const url = parseOriginUrl(raw);
  if (!url || !originAllowed(url) || !protocolOk(url)) return null;
  return `${url.protocol}//${url.host}`;
}

/** Resolve inject/default base; never uses DOM input. */
export function pickApiBase(injectedRaw) {
  const fromInject = resolveApiBase(injectedRaw);
  if (fromInject) return fromInject;
  return ALLOWED_LOCAL_BASES[0];
}
