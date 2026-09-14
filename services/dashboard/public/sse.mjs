/**
 * Pure SSE / API-origin helpers (unit-tested). Used by the operator shell.
 */

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

/** Hosts allowed for operator API origin (local + product domains). */
export function isAllowedApiHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  if (host === "localhost" || host === "127.0.0.1" || host === "[::1]") {
    return true;
  }
  return host === "ibexharness.com" || host.endsWith(".ibexharness.com");
}

/**
 * Normalize and allowlist an API origin. Returns null when invalid.
 * Only http/https; no credentials/userinfo in the URL.
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
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return null;
  }
  if (url.username || url.password) {
    return null;
  }
  if (!isAllowedApiHost(url.hostname)) {
    return null;
  }
  return `${url.protocol}//${url.host}`;
}
