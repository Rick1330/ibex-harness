import type { ZodType } from "zod";

export const BENCHMARK_JSON_SWR_OPTIONS = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  dedupingInterval: 60_000,
} as const;

export async function parseBenchmarkJsonResponse<T>(
  response: Response,
  schema: ZodType<T>,
): Promise<T> {
  if (!response.ok) {
    throw new Error(`Failed to load benchmark data (${response.status})`);
  }
  let json: unknown;
  try {
    json = await response.json();
  } catch (error) {
    throw new Error("Failed to parse benchmark data JSON", { cause: error });
  }
  return schema.parse(json);
}

export async function loadBenchmarkJson<T>(
  request: () => Promise<Response>,
  schema: ZodType<T>,
): Promise<T> {
  try {
    const response = await request();
    return await parseBenchmarkJsonResponse(response, schema);
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error("Failed to load benchmark data", { cause: error });
  }
}
