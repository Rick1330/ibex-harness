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

  it("rejects out-of-range gate_summary metrics", () => {
    const parsed = hnswBenchmarkDataSchema.safeParse({
      schema_version: 1,
      benchmark: "hnsw_recall_latency",
      runs: [
        {
          sha: "abcdef0",
          short_sha: "abcdef0",
          timestamp: "2026-08-26T12:00:00.000Z",
          branch: "main",
          run_number: 1,
          run_url: "https://example.test/run",
          methodology: {},
          mean_recall_at_10: 1,
          results: [
            {
              corpus_size: 10_000,
              query_count: 500,
              recall_at_10: 1,
              latency_ms_p50: 1,
              latency_ms_p95: 2,
              latency_ms_p99: 3,
              ef_search: 40,
            },
          ],
          gate_summary: {
            recall_floor: 1.5,
            worst_recall_at_10: -0.1,
            p95_ms_1m: -1,
            p99_ms_1m: -2,
          },
        },
      ],
    });
    expect(parsed.success).toBe(false);
  });
});
