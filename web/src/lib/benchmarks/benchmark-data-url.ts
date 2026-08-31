/** Same-origin published benchmark JSON paths only (blocks SSRF via fetch). */
const BENCHMARK_DATA_URL_PATTERN = /^\/benchmarks\/[a-z0-9-]+\.json$/;

export function assertSafeBenchmarkDataUrl(url: string): string {
  if (!BENCHMARK_DATA_URL_PATTERN.test(url)) {
    throw new Error(`Invalid benchmark data URL: ${url}`);
  }
  return url;
}
