import { execSync } from "node:child_process";
import process from "node:process";

import { isDocsAppNextProcess, listNodeProcesses } from "./node-process-utils.mjs";

const matches = listNodeProcesses().filter((entry) =>
  isDocsAppNextProcess(entry.command),
);

if (matches.length === 0) {
  console.log("[stop:next] No docs/app Next.js processes found.");
  process.exit(0);
}

for (const entry of matches) {
  try {
    process.kill(entry.pid);
    console.log(`[stop:next] Stopped pid ${entry.pid}`);
  } catch (error) {
    if (process.platform === "win32") {
      execSync(`taskkill /PID ${entry.pid} /F`, { stdio: "ignore" });
      console.log(`[stop:next] Force-stopped pid ${entry.pid}`);
    } else {
      console.warn(`[stop:next] Could not stop pid ${entry.pid}:`, error);
    }
  }
}
