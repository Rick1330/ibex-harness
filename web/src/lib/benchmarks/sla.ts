import { K6_TARGETS } from "./constants";
import type { K6Result } from "./types";

export function k6PassesSla(k6: K6Result): boolean {
  return k6.p99_ms < K6_TARGETS.p99_ms && k6.error_rate < K6_TARGETS.error_rate;
}

export function k6MeetsThroughput(k6: K6Result): boolean {
  return k6.req_per_s >= K6_TARGETS.req_per_s;
}
