/* global __ENV */
import http from "k6/http";
import { check, sleep } from "k6";

// CI (benchmark.yml) probes /health until Phase 2 middleware is complete.
// Phase 2 gate (2.6.1 / 2.6.2): set K6_USE_CHAT=1 to POST /v1/chat/completions
// through the full proxy chain. Health alone does not satisfy that gate.

export const options = {
  vus: Number(__ENV.K6_VUS || 100),
  duration: __ENV.K6_DURATION || "2m",
  thresholds: {
    http_req_duration: ["p(99)<20"],
    http_req_failed: ["rate<0.001"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:18082";
const USE_CHAT = __ENV.K6_USE_CHAT === "1" || __ENV.K6_USE_CHAT === "true";
const HEALTH_PATH = __ENV.K6_HEALTH_PATH || "/health";
const CHAT_PATH = __ENV.K6_CHAT_PATH || "/v1/chat/completions";
const TOKEN = __ENV.IBEX_DEV_TOKEN || __ENV.K6_TOKEN || "";
const AGENT_ID = __ENV.IBEX_DEV_AGENT_ID || __ENV.K6_AGENT_ID || "";

const chatBody = JSON.stringify({
  model: __ENV.K6_MODEL || "gpt-4o-mini",
  messages: [{ role: "user", content: "ping" }],
  stream: false,
});

function probeHealth() {
  const res = http.get(`${BASE_URL}${HEALTH_PATH}`);
  check(res, {
    "status is 200": (r) => r.status === 200,
  });
}

function probeChat() {
  const headers = {
    "Content-Type": "application/json",
  };
  if (TOKEN) {
    headers.Authorization = `Bearer ${TOKEN}`;
  }
  if (AGENT_ID) {
    headers["X-IBEX-Agent-ID"] = AGENT_ID;
  }
  const res = http.post(`${BASE_URL}${CHAT_PATH}`, chatBody, { headers });
  check(res, {
    "chat status ok": (r) => r.status === 200 || r.status === 501,
  });
}

export default function benchmarkLoadScenario() {
  if (USE_CHAT) {
    probeChat();
  } else {
    probeHealth();
  }
  sleep(0.01);
}
