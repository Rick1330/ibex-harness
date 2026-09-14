/**
 * Operator connection-state shell (4.P.0).
 * No secrets in URL/query; PAT lives only in the password field until login.
 * API origin is inject/default only — never read from the DOM for fetch (Codacy SSRF).
 */

import {
  ALLOWED_LOCAL_BASES,
  buildLoginBody,
  parseSSEBlock,
  pickApiBase,
  shouldAcceptEventId,
} from "./sse.mjs";

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

const PATHS = Object.freeze({
  login: "/v1/operator/session/login",
  me: "/v1/operator/session/me",
  logout: "/v1/operator/session/logout",
  stream: "/v1/operator/events/stream",
});

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
const ALLOWED_BASES = Object.freeze([...ALLOWED_LOCAL_BASES, API_BASE]);

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

function apiUrl(path) {
  if (!ALLOWED_BASES.includes(API_BASE)) {
    throw new Error("API origin is not on the allowlist");
  }
  return `${API_BASE}${path}`;
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
  const resp = await fetch(apiUrl(PATHS.login), {
    method: "POST",
    credentials: "include",
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
  const resp = await fetch(apiUrl(PATHS.me), { credentials: "include" });
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

function classifyStreamStatus(resp) {
  if (resp.status === 503 && resp.headers.get("X-IBEX-Drain") === "1") {
    return "drained";
  }
  if (resp.status === 401 || resp.status === 403) {
    return "auth";
  }
  if (resp.status === 429) {
    return "retry";
  }
  if (resp.status >= 400 && resp.status < 500) {
    return "stop";
  }
  if (!resp.ok || !resp.body) {
    return "retry";
  }
  return "ok";
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

function onStreamOutcome(outcome, generation, retryAfter) {
  if (outcome === "retry") {
    scheduleReconnect(generation, retryAfter);
    return;
  }
  if (outcome === "ended" && generation === streamGeneration && !deliberateClose) {
    setState("reconnecting", "SSE ended; will retry");
    scheduleReconnect(generation, null);
  }
}

async function openStream(generation, signal) {
  if (lastEventId != null && generation === streamGeneration) {
    setState("historical", `Resuming after id ${lastEventId}`);
  }
  try {
    const resp = await fetch(apiUrl(PATHS.stream), {
      credentials: "include",
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

function reconnectDelayMs(retryAfterHeader) {
  if (retryAfterHeader) {
    const secs = Number(retryAfterHeader);
    if (Number.isFinite(secs) && secs >= 0) {
      return Math.min(secs * 1000, 60_000);
    }
  }
  const base = Math.min(1000 * 2 ** reconnectAttempt, 30_000);
  const jitter = Math.floor(Math.random() * 250);
  return base + jitter;
}

function scheduleReconnect(generation, retryAfterHeader) {
  if (deliberateClose || generation !== streamGeneration) return;
  if (reconnectTimer) return;
  const delay = reconnectDelayMs(retryAfterHeader);
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
  const resp = await fetch(apiUrl(PATHS.logout), {
    method: "POST",
    credentials: "include",
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
