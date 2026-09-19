/**
 * SSE stream status + reconnect delay helpers (unit-tested).
 */

/** Map an HTTP SSE response to a stream control kind. */
export function classifyStreamStatus(resp) {
  if (isDrainResponse(resp)) return "drained";
  if (isAuthFailure(resp.status)) return "auth";
  if (resp.status === 429) return "retry";
  if (isPermanentClientError(resp.status)) return "stop";
  if (!resp.ok || !resp.body) return "retry";
  return "ok";
}

export function isDrainResponse(resp) {
  return resp.status === 503 && resp.headers.get("X-IBEX-Drain") === "1";
}

export function isAuthFailure(status) {
  return status === 401 || status === 403;
}

export function isPermanentClientError(status) {
  return (
    status >= 400 &&
    status < 500 &&
    status !== 401 &&
    status !== 403 &&
    status !== 408 &&
    status !== 429
  );
}

/** Uniform jitter in [0, maxExclusive) via Web Crypto (not Math.random). */
export function secureJitterMs(maxExclusive) {
  const bound = Math.max(1, Math.floor(maxExclusive));
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0] % bound;
}

/**
 * Reconnect delay: honor Retry-After when present, else exponential backoff + jitter.
 * @param {number} attempt zero-based reconnect attempt
 * @param {string|null|undefined} retryAfterHeader
 */
export function reconnectDelayMs(attempt, retryAfterHeader) {
  if (retryAfterHeader) {
    const secs = Number(retryAfterHeader);
    if (Number.isFinite(secs) && secs >= 0) {
      return Math.min(secs * 1000, 60_000);
    }
  }
  const exp = Math.min(Math.max(0, attempt), 15);
  const base = Math.min(1000 * 2 ** exp, 30_000);
  return base + secureJitterMs(250);
}
