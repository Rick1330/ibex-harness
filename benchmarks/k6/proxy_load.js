/* global __ENV */
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.K6_VUS || 100),
  duration: __ENV.K6_DURATION || "2m",
  thresholds: {
    http_req_duration: ["p(99)<20"],
    http_req_failed: ["rate<0.001"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:18082";
const HEALTH_PATH = __ENV.K6_HEALTH_PATH || "/health";

export default function benchmarkLoadScenario() {
  const res = http.get(`${BASE_URL}${HEALTH_PATH}`);
  check(res, {
    "status is 200": (r) => r.status === 200,
  });
  sleep(0.01);
}
