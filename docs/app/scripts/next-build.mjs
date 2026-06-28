import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { renameIgnoreMissing } from "./build-script-utils.mjs";

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
if (!existingNodeOptions.includes("max-old-space-size")) {
  process.env.NODE_OPTIONS = `${existingNodeOptions} --max-old-space-size=8192`.trim();
}

function runNextBuild(phase) {
  console.log(`[build] ${phase}`);
  const result = spawnSync(process.execPath, [nextBin, "build"], {
    stdio: "inherit",
    shell: false,
    env: process.env,
  });
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

  const buildId = (await readFile(path.join(appRoot, ".next", "BUILD_ID"), "utf8")).trim();
  process.env.NEXT_PUBLIC_SEARCH_INDEX_URL = `/search-index.${buildId}.json`;
  process.env.NEXT_STATIC_EXPORT = "1";

  await stashApiRoutes();
  try {
    runNextBuild("phase 2/2 — static export to out/");
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
