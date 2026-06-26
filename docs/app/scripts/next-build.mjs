import { spawnSync } from "node:child_process";
import process from "node:process";

const disableCache = process.argv.includes("--no-cache");
if (disableCache) {
  process.env.NEXT_DISABLE_WEBPACK_CACHE = "1";
  console.log("[build] Webpack disk cache disabled (--no-cache).");
}

const existingNodeOptions = process.env.NODE_OPTIONS ?? "";
if (!existingNodeOptions.includes("max-old-space-size")) {
  process.env.NODE_OPTIONS = `${existingNodeOptions} --max-old-space-size=8192`.trim();
}

const result = spawnSync("next", ["build"], {
  stdio: "inherit",
  shell: true,
  env: process.env,
});

process.exit(result.status ?? 1);
