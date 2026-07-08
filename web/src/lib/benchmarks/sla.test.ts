import { describe, expect, it } from "vitest";
import { k6MeetsThroughput, k6PassesSla } from "./sla";
import type { K6Result } from "./types";

const passingK6: K6Result = {
  vus: 100,
  duration_s: 120,
  p50_ms: 2.5,
  p95_ms: 8,
  p99_ms: 12,
  p999_ms: 15,
  req_per_s: 8500,
  error_rate: 0,
  check_rate: 1,
};

describe("k6PassesSla", () => {
  it("returns true when p99 and error rate are within targets", () => {
    expect(k6PassesSla(passingK6)).toBe(true);
  });

  it("returns false when p99 exceeds target", () => {
    expect(k6PassesSla({ ...passingK6, p99_ms: 25 })).toBe(false);
  });
});

describe("k6MeetsThroughput", () => {
  it("returns true when req/s meets minimum", () => {
    expect(k6MeetsThroughput(passingK6)).toBe(true);
  });

  it("returns false when throughput is too low", () => {
    expect(k6MeetsThroughput({ ...passingK6, req_per_s: 100 })).toBe(false);
  });
});
