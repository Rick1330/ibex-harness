import { describe, expect, it } from "vitest";

import { loadPublishedHnswBenchmarkData } from "./hnsw-published-data";
import { hnswBenchmarkDataSchema } from "./hnsw-schema";

describe("hnsw published data", () => {
  it("loads committed published JSON successfully", () => {
    const loaded = loadPublishedHnswBenchmarkData();
    expect(loaded.ok).toBe(true);
    if (!loaded.ok) {
      return;
    }
    expect(loaded.data.runs.length).toBeGreaterThan(0);
    expect(loaded.data.runs[0]?.results.some((r) => r.corpus_size === 10_000)).toBe(true);
  });

  it("rejects malformed published payloads", () => {
    const parsed = hnswBenchmarkDataSchema.safeParse({
      schema_version: 1,
      benchmark: "hnsw_recall_latency",
      runs: [
        {
          sha: "abc",
          short_sha: "abc",
          timestamp: "now",
          branch: "main",
          run_number: 0,
          run_url: "",
          methodology: {},
          results: [],
          mean_recall_at_10: 1,
        },
      ],
    });
    expect(parsed.success).toBe(false);
  });
});
