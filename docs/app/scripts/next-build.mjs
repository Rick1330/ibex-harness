import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";

const require = createRequire(import.meta.url);
const nextBin = path.join(
  path.dirname(require.resolve("next/package.json")),
  "dist/bin/next",
);

const disableCache = process.argv.includes("--no-cache");
if (disableCache) {
  process.env.NEXT_DISABLE_WEBPACK_CACHE = "1";
  console.log("[build] Webpack disk cache disabled (--no-cache).");
}

const existingNodeOptions = process.env.NODE_OPTIONS ?? "";
if (!existingNodeOptions.includes("max-old-space-size")) {
  process.env.NODE_OPTIONS = `${existingNodeOptions} --max-old-space-size=8192`.trim();
}

const result = spawnSync(process.execPath, [nextBin, "build"], {
  stdio: "inherit",
  shell: false,
  env: process.env,
});

process.exit(result.status ?? 1);
