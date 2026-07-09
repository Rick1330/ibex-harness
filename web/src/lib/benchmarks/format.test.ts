import { describe, expect, it } from "vitest";
import {
  formatDeltaPct,
  formatLatencyMs,
  formatMs,
  formatNsPerOp,
  formatPercent,
  formatReqPerSec,
} from "./format";

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

describe("formatLatencyMs", () => {
  it("formats nanoseconds for tiny stage values", () => {
    expect(formatLatencyMs(0.00005)).toBe("50 ns");
  });

  it("formats microseconds for sub-0.01 ms values", () => {
    expect(formatLatencyMs(0.00042)).toBe("0.42 µs");
  });

  it("formats milliseconds for larger values", () => {
    expect(formatLatencyMs(8.5)).toBe("8.50 ms");
  });
});

describe("formatNsPerOp", () => {
  it("formats nanoseconds per op", () => {
    expect(formatNsPerOp(376.4)).toBe("376.4 ns/op");
  });

  it("formats milliseconds per op", () => {
    expect(formatNsPerOp(8_500_000)).toBe("8.50 ms/op");
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
