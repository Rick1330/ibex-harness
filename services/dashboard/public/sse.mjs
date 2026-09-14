/**
 * Pure SSE / API-origin helpers (unit-tested). Used by the operator shell.
 */

export const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** Known-safe local defaults used when no inject config is present. */
export const ALLOWED_LOCAL_BASES = Object.freeze([
  "http://localhost:8010",
  "http://127.0.0.1:8010",
]);

export function parseSSEBlock(block) {
  if (!block.trim() || block.startsWith(":")) {
    return null;
  }
  let id = null;
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  const numericId = id != null && id !== "" && Number.isFinite(Number(id)) ? Number(id) : null;
  return { id: numericId, rawId: id, data };
}

export function shouldAcceptEventId(lastEventId, nextId) {
  if (nextId == null) return true;
  if (lastEventId == null) return true;
  return nextId > lastEventId;
}

export function buildLoginBody(pat) {
  return JSON.stringify({ pat: String(pat).trim() });
}

export function isLoopbackHost(hostname) {
  return LOOPBACK_HOSTS.has(String(hostname || "").toLowerCase());
}

/** Hosts allowed for operator API origin (local + product domains). */
export function isAllowedApiHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  if (isLoopbackHost(host)) return true;
  return host === "ibexharness.com" || host.endsWith(".ibexharness.com");
}

/**
 * Normalize and allowlist an API origin. Returns null when invalid.
 * HTTP only for loopback; HTTPS required for all other hosts.
 */
export function resolveApiBase(raw) {
  const trimmed = String(raw || "").trim().replace(/\/$/, "");
  if (!trimmed) return null;
  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.username || url.password) {
    return null;
  }
  if (!isAllowedApiHost(url.hostname)) {
    return null;
  }
  const loopback = isLoopbackHost(url.hostname);
  if (url.protocol === "http:") {
    return loopback ? `${url.protocol}//${url.host}` : null;
  }
  if (url.protocol === "https:") {
    return `${url.protocol}//${url.host}`;
  }
  return null;
}

/** Resolve inject/default base; never uses DOM input. */
export function pickApiBase(injectedRaw) {
  const fromInject = resolveApiBase(injectedRaw);
  if (fromInject) return fromInject;
  return ALLOWED_LOCAL_BASES[0];
}
