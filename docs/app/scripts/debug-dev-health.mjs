import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { listNodeProcesses, isDocsAppNextProcess } from "./node-process-utils.mjs";
import { DEFAULT_DIST, FALLBACK_DIST, isTraceWritable } from "./resolve-dist-dir.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.join(root, "..");
const logPath = path.join(appRoot, "..", "..", "..", "debug-9aa172.log");
const nextDir = path.join(appRoot, ".next");

function log(hypothesisId, message, data) {
  const entry = {
    sessionId: "9aa172",
    hypothesisId,
    location: "scripts/debug-dev-health.mjs",
    message,
    data,
    timestamp: Date.now(),
    runId: process.env.DEBUG_RUN_ID ?? "pre-fix",
  };
  fs.appendFileSync(logPath, `${JSON.stringify(entry)}\n`);
}

function dirStats(dir) {
  if (!fs.existsSync(dir)) {
    return { exists: false, fileCount: 0 };
  }
  let fileCount = 0;
  const stack = [dir];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else {
        fileCount += 1;
      }
    }
  }
  return { exists: true, fileCount };
}

function traceWritable() {
  const tracePath = path.join(nextDir, "trace");
  try {
    fs.mkdirSync(nextDir, { recursive: true });
    fs.writeFileSync(tracePath, "probe\n", { flag: "a" });
    return { writable: true, tracePath };
  } catch (error) {
    return {
      writable: false,
      tracePath,
      code: error.code,
      message: error.message,
    };
  }
}

const nextProcesses = listNodeProcesses().filter((entry) =>
  isDocsAppNextProcess(entry.command),
);

log("H2", "next process scan", {
  count: nextProcesses.length,
  pids: nextProcesses.map((entry) => entry.pid),
});

log("H1", ".next directory state", {
  stats: dirStats(nextDir),
  hasServer: fs.existsSync(path.join(nextDir, "server")),
  hasStatic: fs.existsSync(path.join(nextDir, "static")),
});

const chunk611 = path.join(nextDir, "server", "chunks", "611.js");
log("H1", "webpack chunk 611 presence", {
  exists: fs.existsSync(chunk611),
  path: chunk611,
});

log("H2", "trace file write probe", traceWritable());

log("H2", "dist dir resolution", {
  defaultWritable: isTraceWritable(DEFAULT_DIST),
  fallbackWritable: isTraceWritable(FALLBACK_DIST),
  wouldUse: isTraceWritable(DEFAULT_DIST) ? DEFAULT_DIST : FALLBACK_DIST,
});

const serverManifest = path.join(nextDir, "server", "app-paths-manifest.json");
if (fs.existsSync(serverManifest)) {
  log("H3", "app paths manifest", {
    content: fs.readFileSync(serverManifest, "utf8").slice(0, 500),
  });
}

console.log(`[debug-dev-health] Wrote diagnostics to ${logPath}`);
