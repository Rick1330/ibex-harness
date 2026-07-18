import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { renameIgnoreMissing } from "./build-script-utils.mjs";
import { resolveNodeHeapMb } from "./node-heap.mjs";
import { sanitizeRscTxtFiles } from "./sanitize-rsc-txt.mjs";

const require = createRequire(import.meta.url);
const nextBin = path.join(
  path.dirname(require.resolve("next/package.json")),
  "dist/bin/next",
);

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const apiDir = path.join(appRoot, "src", "app", "api");
const apiStashDir = path.join(appRoot, ".api-build-stash");
const extractScript = path.join(scriptDir, "extract-search-index.mjs");

const disableCache = process.argv.includes("--no-cache");
if (disableCache) {
  process.env.NEXT_DISABLE_WEBPACK_CACHE = "1";
  console.log("[build] Webpack disk cache disabled (--no-cache).");
}

const existingNodeOptions = process.env.NODE_OPTIONS ?? "";
const stripped = existingNodeOptions
  .split(/\s+/)
  .filter(Boolean)
  .filter(
    (flag) =>
      !flag.includes("max-old-space-size") &&
      !flag.includes("max_old_space_size"),
  )
  .join(" ");
const heapMb = resolveNodeHeapMb(process.env.IBEX_NODE_HEAP_MB);
// Main process only — avoid NODE_OPTIONS inheritance into build workers.
process.env.NODE_OPTIONS = stripped;

function runNextBuild(phase) {
  console.log(`[build] ${phase}`);
  const result = spawnSync(
    process.execPath,
    [`--max-old-space-size=${heapMb}`, nextBin, "build"],
    {
      stdio: "inherit",
      shell: false,
      env: process.env,
    },
  );
  if (result.status !== 0) {
    throw new Error(`${phase} failed with exit code ${result.status ?? 1}`);
  }
}

async function stashApiRoutes() {
  await renameIgnoreMissing(
    apiDir,
    apiStashDir,
    "[build] stashed src/app/api for static export",
  );
}

async function restoreApiRoutes() {
  await renameIgnoreMissing(
    apiStashDir,
    apiDir,
    "[build] restored src/app/api after static export",
  );
}

async function main() {
  // Phase 1: standard build so `next start` can serve /api/search for index extraction.
  runNextBuild("phase 1/2 — compile app for search extract");

  const extract = spawnSync(process.execPath, [extractScript], {
    stdio: "inherit",
    shell: false,
    env: process.env,
  });
  if (extract.status !== 0) {
    throw new Error(`search extract failed with exit code ${extract.status ?? 1}`);
  }

  // Client always loads /search-index.json (stable). extract-search-index also writes
  // a build-id copy for immutable cache headers; do not bake the versioned path into
  // the static export — phase 2 gets a new BUILD_ID and the versioned file 404s.
  process.env.NEXT_STATIC_EXPORT = "1";

  await stashApiRoutes();
  try {
    runNextBuild("phase 2/2 — static export to out/");
    const { sanitized } = await sanitizeRscTxtFiles();
    console.log(`[build] sanitized ${sanitized} RSC prefetch .txt file(s)`);
  } finally {
    await restoreApiRoutes();
  }
}

try {
  await main();
} catch (error) {
  console.error("[build] failed:", error);
  await restoreApiRoutes();
  process.exit(1);
}
