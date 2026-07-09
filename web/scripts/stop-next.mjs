import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

import { isDocsAppNextProcess, listNodeProcesses } from "./node-process-utils.mjs";

function taskkillPath() {
  const systemRoot = process.env.SystemRoot ?? "C:\\Windows";
  return path.join(systemRoot, "System32", "taskkill.exe");
}

function stopProcess(pid) {
  const safePid = Number(pid);
  if (!Number.isInteger(safePid) || safePid <= 0) {
    return;
  }

  try {
    process.kill(safePid, "SIGTERM"); // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process
    console.log(`[stop:next] Stopped pid ${safePid}`);
    return;
  } catch (error) {
    if (process.platform !== "win32") {
      console.warn(`[stop:next] Could not stop pid ${safePid}:`, error);
      return;
    }
  }

  spawnSync(taskkillPath(), ["/PID", String(safePid), "/F"], { // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process
    stdio: "ignore",
    shell: false,
  });
  console.log(`[stop:next] Force-stopped pid ${safePid}`);
}

const matches = listNodeProcesses().filter((entry) =>
  isDocsAppNextProcess(entry.command),
);

if (matches.length === 0) {
  console.log("[stop:next] No web Next.js processes found.");
  process.exit(0);
}

for (const entry of matches) {
  stopProcess(entry.pid);
}
