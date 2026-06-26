import { execSync } from "node:child_process";
import process from "node:process";

const TARGET =
  /ibex-harness[\\/]+docs[\\/]+app.*\bnext\s+(dev|build|start)\b/i;

function listNodeProcesses() {
  if (process.platform !== "win32") {
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
  }

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
}

const matches = listNodeProcesses().filter((entry) => TARGET.test(entry.command));
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
