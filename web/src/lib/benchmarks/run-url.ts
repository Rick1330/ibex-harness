import { z } from "zod";

const GITHUB_ACTIONS_RUN_URL =
  /^https:\/\/github\.com\/[^/]+\/[^/]+\/actions\/runs\/\d+$/;

export const benchmarkRunUrlSchema = z
  .string()
  .refine(
    (value) => value === "" || GITHUB_ACTIONS_RUN_URL.test(value),
    "run_url must be empty or a GitHub Actions workflow run URL",
  );

export function isSafeBenchmarkRunUrl(url: string): boolean {
  return benchmarkRunUrlSchema.safeParse(url).success;
}
