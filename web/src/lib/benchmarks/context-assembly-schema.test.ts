import { describe, expect, it } from "vitest";

import { contextAssemblyBenchmarkDataSchema } from "./context-assembly-schema";
import { parseBenchmarkJsonResponse } from "./parse-json-response";

const stubResult = {
  profile: "stub",
  rps: 500,
  duration_s: 10,
  attempted: 5,
  succeeded: 4,
  failed: 1,
  error_rate: 0.2,
  mean_ms: 2.5,
  p50_ms: 2,
  p95_ms: 3,
  p99_ms: 3,
};

describe("context-assembly schema", () => {
  it("accepts a stub artifact through the benchmark JSON parser", async () => {
    const parsed = await parseBenchmarkJsonResponse(
      new Response(JSON.stringify(stubResult), {
        headers: { "content-type": "application/json" },
      }),
      contextAssemblyBenchmarkDataSchema,
    );
    expect(parsed).toEqual(stubResult);
  });

  it.each(Object.keys(stubResult))("rejects a missing %s field", (field) => {
    const malformed: Record<string, unknown> = { ...stubResult };
    delete malformed[field];
    expect(contextAssemblyBenchmarkDataSchema.safeParse(malformed).success).toBe(false);
  });

  it.each(Object.keys(stubResult))("rejects the wrong type for %s", (field) => {
    expect(contextAssemblyBenchmarkDataSchema.safeParse({
      ...stubResult,
      [field]: field === "profile" ? 1 : "invalid",
    }).success).toBe(false);
  });

  it("rejects live results", () => {
    expect(contextAssemblyBenchmarkDataSchema.safeParse({
      ...stubResult,
      profile: "live",
    }).success).toBe(false);
  });

  it("rejects unknown fields", () => {
    expect(contextAssemblyBenchmarkDataSchema.safeParse({
      ...stubResult,
      extra: true,
    }).success).toBe(false);
  });

  it.each([
    ["rps", 0],
    ["rps", 1.5],
    ["duration_s", 0],
    ["attempted", -1],
    ["attempted", 1.5],
    ["succeeded", -1],
    ["succeeded", 1.5],
    ["failed", -1],
    ["failed", 1.5],
    ["error_rate", -0.1],
    ["error_rate", 1.1],
    ["mean_ms", -1],
    ["p50_ms", -1],
    ["p95_ms", -1],
    ["p99_ms", -1],
  ])("rejects %s outside its bounds (%s)", (field, value) => {
    expect(contextAssemblyBenchmarkDataSchema.safeParse({
      ...stubResult,
      [field]: value,
    }).success).toBe(false);
  });

  it.each(["rps", "attempted", "succeeded", "failed"])(
    "accepts an exactly representable integer above the safe range for %s",
    (field) => {
      expect(contextAssemblyBenchmarkDataSchema.safeParse({
        ...stubResult,
        [field]: 2 ** 53,
      }).success).toBe(true);
    },
  );

  it.each([0, 1])("accepts inclusive bounds at error_rate %s", (errorRate) => {
    expect(contextAssemblyBenchmarkDataSchema.safeParse({
      profile: "stub",
      rps: 1,
      duration_s: 0.1,
      attempted: 0,
      succeeded: 0,
      failed: 0,
      error_rate: errorRate,
      mean_ms: 0,
      p50_ms: 0,
      p95_ms: 0,
      p99_ms: 0,
    }).success).toBe(true);
  });
});
