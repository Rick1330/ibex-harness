/**
 * Operator connection-state shell (4.P.0).
 * PAT lives only in the password field until login; fetch URLs are allowlisted.
 */

import { buildEndpointUrls, pickApiBase } from "./api_base.mjs";
import { createApiFetch } from "./api_fetch.mjs";
import { buildLoginBody } from "./sse.mjs";
import { createSseController } from "./sse_client.mjs";

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
const apiFetch = createApiFetch(buildEndpointUrls(API_BASE));

els.apiBase.value = API_BASE;
els.apiBase.readOnly = true;
els.apiBase.title = injected
  ? "Set by deploy config (IBEX_API_BASE_URL)"
  : "Local default (http://localhost:8010)";

let csrfToken = "";

function setState(name, detail) {
  const next = STATES.has(name) ? name : "unknown";
  els.state.textContent = next;
  els.state.className = `state ${next}`;
  els.detail.textContent = detail || "";
}

function appendEvent(line) {
  const li = document.createElement("li");
  li.textContent = line;
  els.log.prepend(li);
  while (els.log.children.length > 40) {
    els.log.lastChild.remove();
  }
}

const sse = createSseController({ apiFetch, setState, appendEvent });

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

async function logout() {
  sse.close();
  const headers = {};
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const resp = await apiFetch("logout", { method: "POST", headers });
  if (!resp.ok) {
    setState("error", `logout failed: HTTP ${resp.status}`);
    return;
  }
  csrfToken = "";
  sse.resetCursor();
  setState("unauthenticated", "Logged out");
}

document.getElementById("btn-login").addEventListener("click", () => void login());
document.getElementById("btn-me").addEventListener("click", () => void me());
document.getElementById("btn-sse").addEventListener("click", () => sse.connect());
document.getElementById("btn-logout").addEventListener("click", () => void logout());

setState("unauthenticated", "Ready — login with a PAT (not stored in the URL)");
