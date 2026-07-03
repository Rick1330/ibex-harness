import { describe, expect, it } from "vitest";

import { findRunBySha } from "./runs";
import { sampleBenchmarkRun as sampleRun } from "./test-fixtures";

describe("findRunBySha", () => {
  const runs = [sampleRun(), sampleRun({ sha: "abc123def", short_sha: "abc123d" })];

  it("finds by short sha", () => {
    expect(findRunBySha(runs, "bfc0a75")?.short_sha).toBe("bfc0a75");
  });

  it("finds by full sha prefix", () => {
    expect(findRunBySha(runs, "bfc0a75c8e4")?.short_sha).toBe("bfc0a75");
  });

  it("returns null when missing", () => {
    expect(findRunBySha(runs, "missing")).toBeNull();
  });
});
