/**
 * Operator SSE connect / reconnect controller (4.P.0 shell).
 */

import { parseSSEBlock, shouldAcceptEventId } from "./sse.mjs";
import { classifyStreamStatus, reconnectDelayMs } from "./stream.mjs";

/** Clear reconnect backoff only after the stream proves usable. */
export const STABLE_CONNECTION_MS = 10_000;

/**
 * @param {boolean} receivedEvent
 * @param {number} openMs
 * @param {number} [stableMs]
 */
export function shouldClearReconnectBackoff(
  receivedEvent,
  openMs,
  stableMs = STABLE_CONNECTION_MS,
) {
  return Boolean(receivedEvent) || openMs >= stableMs;
}

/**
 * @param {{
 *   apiFetch: (name: string, init?: RequestInit) => Promise<Response>,
 *   setState: (name: string, detail?: string) => void,
 *   appendEvent: (line: string) => void,
 * }} deps
 */
export function createSseController(deps) {
  const { apiFetch, setState, appendEvent } = deps;
  let lastEventId = null;
  let streamGeneration = 0;
  let abortController = null;
  let reconnectTimer = null;
  let deliberateClose = false;
  let reconnectAttempt = 0;

  function abortActive() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
  }

  function close() {
    deliberateClose = true;
    streamGeneration += 1;
    abortActive();
  }

  function resetCursor() {
    lastEventId = null;
  }

  function sseHeaders() {
    const headers = { Accept: "text/event-stream" };
    if (lastEventId != null) headers["Last-Event-ID"] = String(lastEventId);
    return headers;
  }

  function scheduleReconnect(generation, retryAfterHeader) {
    if (deliberateClose || generation !== streamGeneration) return;
    if (reconnectTimer) return;
    const delay = reconnectDelayMs(reconnectAttempt, retryAfterHeader);
    reconnectAttempt += 1;
    setState("reconnecting", `Reconnect in ${Math.round(delay / 1000)}s…`);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      if (deliberateClose || generation !== streamGeneration) return;
      connect();
    }, delay);
  }

  function handleBlock(block, generation, stability) {
    if (generation !== streamGeneration) return;
    const parsed = parseSSEBlock(block);
    if (!parsed) return;
    if (!shouldAcceptEventId(lastEventId, parsed.id)) return;
    if (parsed.id != null) lastEventId = parsed.id;
    appendEvent(parsed.id != null ? `#${parsed.id} ${parsed.data}` : parsed.data);
    setState("live", `last-event-id=${lastEventId}`);
    stability.receivedEvent = true;
    reconnectAttempt = 0;
  }

  async function readBody(body, generation, stability) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    try {
      while (generation === streamGeneration) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const block of parts) handleBlock(block, generation, stability);
      }
    } catch (err) {
      if (generation !== streamGeneration) return;
      throw err;
    }
  }

  async function handleResponse(resp, generation) {
    if (generation !== streamGeneration) return "stale";
    const kind = classifyStreamStatus(resp);
    if (kind === "drained") {
      setState("drained", "API is draining; new SSE rejected");
      return "stop";
    }
    if (kind === "auth") {
      setState("unauthenticated", `SSE rejected: HTTP ${resp.status}`);
      return "stop";
    }
    if (kind === "stop") {
      setState("error", `SSE permanent failure: HTTP ${resp.status}`);
      return "stop";
    }
    if (kind === "retry") {
      setState("degraded", `SSE failed: HTTP ${resp.status}`);
      return { outcome: "retry", retryAfter: resp.headers.get("Retry-After") };
    }
    setState("live", "SSE connected");
    const stability = { receivedEvent: false };
    const openedAt = Date.now();
    await readBody(resp.body, generation, stability);
    const openMs = Date.now() - openedAt;
    if (shouldClearReconnectBackoff(stability.receivedEvent, openMs)) {
      reconnectAttempt = 0;
    }
    return "ended";
  }

  function shouldResume(outcome, generation) {
    if (outcome !== "ended") return false;
    if (generation !== streamGeneration) return false;
    return !deliberateClose;
  }

  function onOutcome(outcome, generation, retryAfter) {
    if (outcome === "retry") {
      scheduleReconnect(generation, retryAfter);
      return;
    }
    if (shouldResume(outcome, generation)) {
      setState("reconnecting", "SSE ended; will retry");
      scheduleReconnect(generation, null);
    }
  }

  async function open(generation, signal) {
    if (lastEventId != null && generation === streamGeneration) {
      setState("historical", `Resuming after id ${lastEventId}`);
    }
    try {
      const resp = await apiFetch("stream", { headers: sseHeaders(), signal });
      const result = await handleResponse(resp, generation);
      if (result && typeof result === "object") {
        onOutcome(result.outcome, generation, result.retryAfter);
        return;
      }
      onOutcome(result, generation, null);
    } catch (err) {
      if (signal.aborted || generation !== streamGeneration) return;
      setState("degraded", `SSE error: ${err}`);
      scheduleReconnect(generation, null);
    }
  }

  function connect() {
    deliberateClose = false;
    abortActive();
    const generation = ++streamGeneration;
    abortController = new AbortController();
    setState(lastEventId ? "reconnecting" : "live", "Opening EventSource…");
    void open(generation, abortController.signal);
  }

  return { connect, close, resetCursor };
}
