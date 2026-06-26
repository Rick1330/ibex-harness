import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

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

const NEXT_START =
  /ibex-harness[\\/]+docs[\\/]+app.*\bnext\s+start\b/i;

function listNodeProcesses() {
  if (process.platform !== "win32") {
    try {
      const out = execSync("ps -ax -o pid=,command=", { encoding: "utf8" });
      return out
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const match = line.match(/^(\d+)\s+(.*)$/);
          if (!match) return null;
          return { pid: Number(match[1]), command: match[2] };
        })
        .filter(Boolean);
    } catch {
      return [];
    }
  }

  try {
    const out = execSync(
      'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name=\'node.exe\'\\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"',
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
    if (!out) return [];
    const parsed = JSON.parse(out);
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    return rows
      .filter((row) => row?.ProcessId && row?.CommandLine)
      .map((row) => ({
        pid: Number(row.ProcessId),
        command: String(row.CommandLine),
      }));
  } catch {
    return [];
  }
}

const selfPids = new Set([process.pid, process.ppid]);
const runningStart = listNodeProcesses().filter(
  (entry) =>
    !selfPids.has(entry.pid) && NEXT_START.test(entry.command),
);

if (runningStart.length > 0) {
  console.warn("\n[start] Another `next start` for docs/app is already running:");
  for (const entry of runningStart) {
    console.warn(`  - pid ${entry.pid}`);
  }
  console.warn("  Stop it first or use a different port.\n");
}
