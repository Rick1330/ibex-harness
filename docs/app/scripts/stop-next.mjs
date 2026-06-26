import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

import { isDocsAppNextProcess, listNodeProcesses } from "./node-process-utils.mjs";

function taskkillPath() {
  const systemRoot = process.env.SystemRoot ?? "C:\\Windows";
  return path.join(systemRoot, "System32", "taskkill.exe");
}

function stopProcess(pid) {
  try {
    process.kill(pid);
    console.log(`[stop:next] Stopped pid ${pid}`);
    return;
  } catch (error) {
    if (process.platform !== "win32") {
      console.warn(`[stop:next] Could not stop pid ${pid}:`, error);
      return;
    }
  }

  spawnSync(taskkillPath(), ["/PID", String(pid), "/F"], { stdio: "ignore" });
  console.log(`[stop:next] Force-stopped pid ${pid}`);
}

const matches = listNodeProcesses().filter((entry) =>
  isDocsAppNextProcess(entry.command),
);

if (matches.length === 0) {
  console.log("[stop:next] No docs/app Next.js processes found.");
  process.exit(0);
}

for (const entry of matches) {
  stopProcess(entry.pid);
}
