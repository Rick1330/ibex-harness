/**
 * Operator connection-state shell (4.P.0).
 * No secrets in URL/query; PAT lives only in the password field until login.
 */

import {
  buildLoginBody,
  parseSSEBlock,
  resolveApiBase,
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

function injectedApiBase() {
  return typeof window.IBEX_API_BASE_URL === "string" ? window.IBEX_API_BASE_URL.trim() : "";
}

function defaultApiBase() {
  return resolveApiBase(injectedApiBase()) || "http://localhost:8010";
}

function initApiBaseField() {
  const injected = injectedApiBase();
  els.apiBase.value = defaultApiBase();
  if (injected) {
    els.apiBase.readOnly = true;
    els.apiBase.title = "Set by deploy config (IBEX_API_BASE_URL)";
  }
}

initApiBaseField();

function setState(name, detail) {
  const next = STATES.has(name) ? name : "unknown";
  els.state.textContent = next;
  els.state.className = `state ${next}`;
  els.detail.textContent = detail || "";
}

function apiUrl(path) {
  const base = resolveApiBase(els.apiBase.value);
  if (!base) {
    throw new Error("API origin is not allowlisted (http/https localhost or *.ibexharness.com)");
  }
  return `${base}${path}`;
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
  let url;
  try {
    url = apiUrl("/v1/operator/session/login");
  } catch (err) {
    setState("error", String(err.message || err));
    return;
  }
  setState("reconnecting", "Exchanging PAT for session cookies…");
  const resp = await fetch(url, {
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
  let url;
  try {
    url = apiUrl("/v1/operator/session/me");
  } catch (err) {
    setState("error", String(err.message || err));
    return;
  }
  const resp = await fetch(url, { credentials: "include" });
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
  let url;
  try {
    url = apiUrl("/v1/operator/events/stream");
  } catch (err) {
    setState("error", String(err.message || err));
    return;
  }
  const generation = ++streamGeneration;
  abortController = new AbortController();
  setState(lastEventId ? "reconnecting" : "live", "Opening EventSource…");
  void streamWithFetch(url, generation, abortController.signal);
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
  if (resp.status === 503 && resp.headers.get("X-IBEX-Drain") === "1") {
    setState("drained", "API is draining; new SSE rejected");
    return "stop";
  }
  if (resp.status === 401 || resp.status === 403) {
    setState("unauthenticated", `SSE rejected: HTTP ${resp.status}`);
    return "stop";
  }
  if (!resp.ok || !resp.body) {
    setState("degraded", `SSE failed: HTTP ${resp.status}`);
    return "retry";
  }
  setState("live", "SSE connected");
  await readStreamBody(resp.body, generation);
  return "ended";
}

async function streamWithFetch(url, generation, signal) {
  if (lastEventId != null && generation === streamGeneration) {
    setState("historical", `Resuming after id ${lastEventId}`);
  }
  try {
    const resp = await fetch(url, {
      credentials: "include",
      headers: sseHeaders(),
      signal,
    });
    const outcome = await handleStreamResponse(resp, generation);
    if (outcome === "retry") {
      scheduleReconnect(generation);
      return;
    }
    if (outcome === "ended" && generation === streamGeneration && !deliberateClose) {
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
  let url;
  try {
    url = apiUrl("/v1/operator/session/logout");
  } catch (err) {
    setState("error", String(err.message || err));
    return;
  }
  const headers = {};
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  await fetch(url, {
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
