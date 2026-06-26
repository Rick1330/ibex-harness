import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

import { isDocsAppNextStart, listNodeProcesses } from "./node-process-utils.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(root, "..");
const buildIdPath = path.resolve(appRoot, ".next", "BUILD_ID");

if (!buildIdPath.startsWith(`${appRoot}${path.sep}`)) {
  console.error("[start] Invalid build path.");
  process.exit(1);
}

if (!fs.existsSync(buildIdPath)) {
  console.error(
    "\n[start] .next/BUILD_ID is missing — the production build did not finish.\n" +
      "  Run: pnpm build:clean\n" +
      "  Wait until the process exits (including 'Finishing writing to cache').\n" +
      "  Do not run start in another tab while build is still running.\n",
  );
  process.exit(1);
}

const selfPids = new Set([process.pid, process.ppid]);
const runningStart = listNodeProcesses().filter(
  (entry) =>
    !selfPids.has(entry.pid) && isDocsAppNextStart(entry.command),
);

if (runningStart.length > 0) {
  console.warn("\n[start] Another `next start` for docs/app is already running:");
  for (const entry of runningStart) {
    console.warn(`  - pid ${entry.pid}`);
  }
  console.warn("  Stop it first or use a different port.\n");
}
