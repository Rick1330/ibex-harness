import { describe, expect, it } from "vitest";
import { formatDeltaPct, formatMs, formatPercent, formatReqPerSec } from "./format";

describe("formatMs", () => {
  it("formats sub-millisecond values", () => {
    expect(formatMs(0.42)).toBe("0.42 ms");
  });

  it("formats millisecond values", () => {
    expect(formatMs(4.643)).toBe("4.64 ms");
  });

  it("returns dash for non-finite values", () => {
    expect(formatMs(Number.NaN)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats fractional rates as percent", () => {
    expect(formatPercent(0.001)).toBe("0.10%");
  });
});

describe("formatReqPerSec", () => {
  it("formats throughput", () => {
    expect(formatReqPerSec(8665.17)).toBe("8,665 req/s");
  });
});

describe("formatDeltaPct", () => {
  it("formats signed delta", () => {
    expect(formatDeltaPct(-2.5)).toBe("-2.5%");
    expect(formatDeltaPct(3.2)).toBe("+3.2%");
  });
});
