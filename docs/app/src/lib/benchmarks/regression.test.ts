import { describe, expect, it } from "vitest";

import { deltaForRun, isRegression, pctChange } from "./regression";

describe("pctChange", () => {
  it("returns positive for degradation when lower is better", () => {
    expect(pctChange(10, 11, false)).toBeCloseTo(10);
  });

  it("returns negative for improvement when lower is better", () => {
    expect(pctChange(10, 9, false)).toBeCloseTo(-10);
  });

  it("inverts for higher-is-better metrics", () => {
    expect(pctChange(9000, 9900, true)).toBeCloseTo(-10);
  });

  it("returns null when baseline is null", () => {
    expect(pctChange(null, 11, false)).toBeNull();
  });
});

describe("isRegression", () => {
  it("returns true when pctChange exceeds threshold", () => {
    expect(isRegression(11)).toBe(true);
  });

  it("returns false when pctChange is within threshold", () => {
    expect(isRegression(9)).toBe(false);
  });
});

describe("deltaForRun", () => {
  it("reads metric delta by key", () => {
    expect(deltaForRun("k6.p99_ms", { "k6.p99_ms": -2.5 })).toBe(-2.5);
  });
});
