/**
 * Measure response time and payload size for key docs routes.
 * Run with production server: pnpm build && pnpm start (in another terminal).
 *
 * Usage: node ./scripts/measure-rsc-payload.mjs [baseUrl]
 */

const baseUrl = process.argv[2] ?? "http://localhost:3000";

const routes = [
  "/docs/getting-started/introduction",
  "/docs/architecture/overview",
  "/docs/proxy/overview",
  "/roadmap/phase-1-5-docs-site/master-brief",
  "/api/search",
];

const budgets = {
  pageMs: 150,
  pageBytes: 115_000,
  roadmapPageBytes: 520_000,
  searchBytes: 4_000_000,
};

async function measureRoute(route) {
  const url = `${baseUrl}${route}`;
  const headers = route.startsWith("/api/")
    ? {}
    : { RSC: "1", Accept: "text/x-component" };

  // Warm cache (production server should serve static flight data quickly).
  await fetch(url, { headers }).catch(() => undefined);

  const started = performance.now();
  const response = await fetch(url, { headers });
  const body = await response.arrayBuffer();
  const elapsed = Math.round(performance.now() - started);

  return {
    route,
    status: response.status,
    ms: elapsed,
    bytes: body.byteLength,
  };
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

console.log(`Measuring ${baseUrl}\n`);

const results = [];
for (const route of routes) {
  try {
    results.push(await measureRoute(route));
  } catch (error) {
    results.push({
      route,
      status: 0,
      ms: -1,
      bytes: 0,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

let failed = 0;

for (const result of results) {
  const line = `${result.route.padEnd(48)} ${String(result.status).padStart(3)}  ${String(result.ms).padStart(5)} ms  ${formatBytes(result.bytes).padStart(10)}`;
  console.log(line);

  if ("error" in result && result.error) {
    console.log(`  error: ${result.error}`);
    failed += 1;
    continue;
  }

  if (result.status !== 200) {
    failed += 1;
    continue;
  }

  if (result.route.startsWith("/api/search")) {
    if (result.bytes > budgets.searchBytes) {
      console.log(`  WARN: search index > ${formatBytes(budgets.searchBytes)}`);
      failed += 1;
    }
    continue;
  }

  const byteBudget = result.route.startsWith("/roadmap/")
    ? budgets.roadmapPageBytes
    : budgets.pageBytes;

  if (result.ms > budgets.pageMs) {
    console.log(`  WARN: slower than ${budgets.pageMs} ms budget`);
    failed += 1;
  }
  if (result.bytes > byteBudget) {
    console.log(`  WARN: payload > ${formatBytes(byteBudget)}`);
    failed += 1;
  }
}

console.log(failed === 0 ? "\nAll checks passed." : `\n${failed} check(s) over budget or failed.`);
process.exit(failed === 0 ? 0 : 1);
