/**
 * Operator connection-state shell (4.P.0).
 * No secrets in URL/query; PAT lives only in the password field until login.
 * Fetch URLs come only from a frozen allowlist (Codacy SSRF).
 */

import { buildEndpointUrls, pickApiBase } from "./api_base.mjs";
import { withCredentialedPolicy } from "./http.mjs";
import { buildLoginBody, parseSSEBlock, shouldAcceptEventId } from "./sse.mjs";
import { classifyStreamStatus, reconnectDelayMs } from "./stream.mjs";

const STATES = new Set([
  "unknown",
  "unauthenticated",
  "connected",
  "reconnecting",
  "degraded",
  "drained",
  "live",
  "historical",
  "error",
]);

const els = {
  state: document.getElementById("conn-state"),
  detail: document.getElementById("conn-detail"),
  log: document.getElementById("event-log"),
  apiBase: document.getElementById("api-base"),
  pat: document.getElementById("pat"),
};

const injected =
  typeof window.IBEX_API_BASE_URL === "string" ? window.IBEX_API_BASE_URL.trim() : "";
const API_BASE = pickApiBase(injected);
const ENDPOINTS = buildEndpointUrls(API_BASE);
const ALLOWED_URLS = Object.freeze(Object.values(ENDPOINTS));

els.apiBase.value = API_BASE;
els.apiBase.readOnly = true;
els.apiBase.title = injected
  ? "Set by deploy config (IBEX_API_BASE_URL)"
  : "Local default (http://localhost:8010)";

let csrfToken = "";
let lastEventId = null;
let streamGeneration = 0;
let abortController = null;
let reconnectTimer = null;
let deliberateClose = false;
let reconnectAttempt = 0;

function setState(name, detail) {
  const next = STATES.has(name) ? name : "unknown";
  els.state.textContent = next;
  els.state.className = `state ${next}`;
  els.detail.textContent = detail || "";
}

function apiFetch(name, init = {}) {
  const url = ENDPOINTS[name];
  if (ALLOWED_URLS.includes(url)) {
    return fetch(url, withCredentialedPolicy(init));
  }
  throw new Error("API endpoint is not on the allowlist");
}

function appendEvent(line) {
  const li = document.createElement("li");
  li.textContent = line;
  els.log.prepend(li);
  while (els.log.children.length > 40) {
    els.log.lastChild.remove();
  }
}

async function login() {
  const pat = els.pat.value.trim();
  if (!pat) {
    setState("error", "PAT required for provisional login stub");
    return;
  }
  setState("reconnecting", "Exchanging PAT for session cookies…");
  const resp = await apiFetch("login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: buildLoginBody(pat),
  });
  els.pat.value = "";
  if (!resp.ok) {
    setState("unauthenticated", `login failed: HTTP ${resp.status}`);
    return;
  }
  const body = await resp.json();
  csrfToken = body.csrf_token || "";
  setState("connected", `org ${body.org_id} (provisional session)`);
}

async function me() {
  const resp = await apiFetch("me");
  if (resp.status === 401 || resp.status === 403) {
    setState("unauthenticated", `/me rejected: HTTP ${resp.status}`);
    return;
  }
  if (!resp.ok) {
    setState("degraded", `/me failed: HTTP ${resp.status}`);
    return;
  }
  const body = await resp.json();
  setState("connected", `authenticated via ${body.auth}; org ${body.org_id}`);
}

function abortActiveStream() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
}

function closeSSE() {
  deliberateClose = true;
  streamGeneration += 1;
  abortActiveStream();
}

function connectSSE() {
  deliberateClose = false;
  abortActiveStream();
  const generation = ++streamGeneration;
  abortController = new AbortController();
  setState(lastEventId ? "reconnecting" : "live", "Opening EventSource…");
  void openStream(generation, abortController.signal);
}

function sseHeaders() {
  const headers = { Accept: "text/event-stream" };
  if (lastEventId != null) {
    headers["Last-Event-ID"] = String(lastEventId);
  }
  return headers;
}

async function handleStreamResponse(resp, generation) {
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
  reconnectAttempt = 0;
  await readStreamBody(resp.body, generation);
  return "ended";
}

function shouldResumeAfterEnd(outcome, generation) {
  if (outcome !== "ended") return false;
  if (generation !== streamGeneration) return false;
  return !deliberateClose;
}

function onStreamOutcome(outcome, generation, retryAfter) {
  if (outcome === "retry") {
    scheduleReconnect(generation, retryAfter);
    return;
  }
  if (shouldResumeAfterEnd(outcome, generation)) {
    setState("reconnecting", "SSE ended; will retry");
    scheduleReconnect(generation, null);
  }
}

async function openStream(generation, signal) {
  if (lastEventId != null && generation === streamGeneration) {
    setState("historical", `Resuming after id ${lastEventId}`);
  }
  try {
    const resp = await apiFetch("stream", {
      headers: sseHeaders(),
      signal,
    });
    const result = await handleStreamResponse(resp, generation);
    if (result && typeof result === "object") {
      onStreamOutcome(result.outcome, generation, result.retryAfter);
      return;
    }
    onStreamOutcome(result, generation, null);
  } catch (err) {
    if (signal.aborted || generation !== streamGeneration) return;
    setState("degraded", `SSE error: ${err}`);
    scheduleReconnect(generation, null);
  }
}

async function readStreamBody(body, generation) {
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
      for (const block of parts) {
        handleSSEBlock(block, generation);
      }
    }
  } catch (err) {
    if (generation !== streamGeneration) return;
    throw err;
  }
}

function handleSSEBlock(block, generation) {
  if (generation !== streamGeneration) return;
  const parsed = parseSSEBlock(block);
  if (!parsed) return;
  if (!shouldAcceptEventId(lastEventId, parsed.id)) return;
  if (parsed.id != null) lastEventId = parsed.id;
  appendEvent(parsed.id != null ? `#${parsed.id} ${parsed.data}` : parsed.data);
  setState("live", `last-event-id=${lastEventId}`);
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
    connectSSE();
  }, delay);
}

async function logout() {
  closeSSE();
  const headers = {};
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const resp = await apiFetch("logout", {
    method: "POST",
    headers,
  });
  if (!resp.ok) {
    setState("error", `logout failed: HTTP ${resp.status}`);
    return;
  }
  csrfToken = "";
  lastEventId = null;
  setState("unauthenticated", "Logged out");
}

document.getElementById("btn-login").addEventListener("click", () => void login());
document.getElementById("btn-me").addEventListener("click", () => void me());
document.getElementById("btn-sse").addEventListener("click", () => connectSSE());
document.getElementById("btn-logout").addEventListener("click", () => void logout());

setState("unauthenticated", "Ready — login with a PAT (not stored in the URL)");
