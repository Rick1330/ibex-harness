import { describe, expect, it } from "vitest";

import { extractionQualityBenchmarkDataSchema } from "./extraction-quality-schema";
import { parseBenchmarkJsonResponse } from "./parse-json-response";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("extraction-quality schema", () => {
  it("accepts empty published history", async () => {
    const parsed = await parseBenchmarkJsonResponse(
      jsonResponse({
        schema_version: 1,
        benchmark: "extraction_quality",
        runs: [],
      }),
      extractionQualityBenchmarkDataSchema,
    );
    expect(parsed.runs).toEqual([]);
  });

  it("rejects unsupported mode values", async () => {
    await expect(
      parseBenchmarkJsonResponse(
        jsonResponse({
          schema_version: 1,
          benchmark: "extraction_quality",
          runs: [
            {
              sha: "abcdef0123456789abcdef0123456789abcdef01",
              short_sha: "abcdef0",
              timestamp: "2026-09-04T00:00:00.000Z",
              branch: "main",
              run_number: 1,
              run_url: "https://github.com/Rick1330/ibex-harness/actions/runs/1",
              mode: "not-a-real-mode",
              metrics: {
                precision_macro: 1,
                recall_macro: 1,
                category_assignment_accuracy: 1,
                temporal_field_accuracy: 1,
              },
              status: "pass",
            },
          ],
        }),
        extractionQualityBenchmarkDataSchema,
      ),
    ).rejects.toThrow();
  });

  it("accepts supported mode enum values", () => {
    const parsed = extractionQualityBenchmarkDataSchema.safeParse({
      schema_version: 1,
      benchmark: "extraction_quality",
      runs: [
        {
          sha: "abcdef0123456789abcdef0123456789abcdef01",
          short_sha: "abcdef0",
          timestamp: "2026-09-04T00:00:00.000Z",
          branch: "main",
          run_number: 1,
          run_url: "https://github.com/Rick1330/ibex-harness/actions/runs/1",
          mode: "cassette",
          metrics: {
            precision_macro: 1,
            recall_macro: 1,
            category_assignment_accuracy: 1,
            temporal_field_accuracy: 1,
          },
          status: "pass",
        },
      ],
    });
    expect(parsed.success).toBe(true);
  });
});
