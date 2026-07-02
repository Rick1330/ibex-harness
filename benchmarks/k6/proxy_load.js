/* global __ENV */
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 100,
  duration: "2m",
  thresholds: {
    http_req_duration: ["p(99)<20"],
    http_req_failed: ["rate<0.001"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:18082";

export default function benchmarkLoadScenario() {
  const res = http.get(`${BASE_URL}/healthz`);
  check(res, {
    "status is 200": (r) => r.status === 200,
  });
  sleep(0.01);
}
