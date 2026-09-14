/**
 * Operator connection-state shell (4.P.0).
 * No secrets in URL/query; PAT lives only in the password field until login.
 */

import { buildLoginBody, parseSSEBlock, shouldAcceptEventId } from "./sse.mjs";

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

let csrfToken = "";
let lastEventId = null;
let streamGeneration = 0;
let abortController = null;
let reconnectTimer = null;
let deliberateClose = false;

function defaultApiBase() {
  // Same-site with UI on http://localhost:3100 — use localhost, not 127.0.0.1.
  return window.IBEX_API_BASE_URL || "http://localhost:8010";
}

els.apiBase.value = defaultApiBase();

function setState(name, detail) {
  const next = STATES.has(name) ? name : "unknown";
  els.state.textContent = next;
  els.state.className = `state ${next}`;
  els.detail.textContent = detail || "";
}

function apiUrl(path) {
  return `${els.apiBase.value.replace(/\/$/, "")}${path}`;
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
  const resp = await fetch(apiUrl("/v1/operator/session/login"), {
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
  const resp = await fetch(apiUrl("/v1/operator/session/me"), {
    credentials: "include",
  });
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
  const url = apiUrl("/v1/operator/events/stream");
  setState(lastEventId ? "reconnecting" : "live", "Opening EventSource…");
  void streamWithFetch(url, generation, abortController.signal);
}

async function streamWithFetch(url, generation, signal) {
  const headers = { Accept: "text/event-stream" };
  if (lastEventId != null) {
    headers["Last-Event-ID"] = String(lastEventId);
    if (generation === streamGeneration) {
      setState("historical", `Resuming after id ${lastEventId}`);
    }
  }
  try {
    const resp = await fetch(url, { credentials: "include", headers, signal });
    if (generation !== streamGeneration) return;
    if (resp.status === 503 && resp.headers.get("X-IBEX-Drain") === "1") {
      setState("drained", "API is draining; new SSE rejected");
      return;
    }
    if (resp.status === 401 || resp.status === 403) {
      setState("unauthenticated", `SSE rejected: HTTP ${resp.status}`);
      return;
    }
    if (!resp.ok || !resp.body) {
      setState("degraded", `SSE failed: HTTP ${resp.status}`);
      scheduleReconnect(generation);
      return;
    }
    setState("live", "SSE connected");
    await readStreamBody(resp.body, generation);
    if (generation === streamGeneration && !deliberateClose) {
      setState("reconnecting", "SSE ended; will retry");
      scheduleReconnect(generation);
    }
  } catch (err) {
    if (signal.aborted || generation !== streamGeneration) return;
    setState("degraded", `SSE error: ${err}`);
    scheduleReconnect(generation);
  }
}

async function readStreamBody(body, generation) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let aborted = false;
  while (!aborted && generation === streamGeneration) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const block of parts) {
      handleSSEBlock(block, generation);
    }
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

function scheduleReconnect(generation) {
  if (deliberateClose || generation !== streamGeneration) return;
  if (reconnectTimer) return;
  setState("reconnecting", "Reconnect in 2s…");
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (deliberateClose || generation !== streamGeneration) return;
    connectSSE();
  }, 2000);
}

async function logout() {
  closeSSE();
  const headers = {};
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  await fetch(apiUrl("/v1/operator/session/logout"), {
    method: "POST",
    credentials: "include",
    headers,
  });
  csrfToken = "";
  lastEventId = null;
  setState("unauthenticated", "Logged out");
}

document.getElementById("btn-login").addEventListener("click", () => void login());
document.getElementById("btn-me").addEventListener("click", () => void me());
document.getElementById("btn-sse").addEventListener("click", () => connectSSE());
document.getElementById("btn-logout").addEventListener("click", () => void logout());

setState("unauthenticated", "Ready — login with a PAT (not stored in the URL)");
