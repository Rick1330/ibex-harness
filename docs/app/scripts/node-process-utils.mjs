import { execSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

const NEXT_CMD = /\bnext\s+(dev|build|start)\b/i;
const NEXT_START_CMD = /\bnext\s+start\b/i;

export function getDocsAppRoot() {
  return path.resolve(process.cwd()).replace(/\\/g, "/");
}

export function listNodeProcesses() {
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

export function isDocsAppNextProcess(command, docsAppRoot = getDocsAppRoot()) {
  if (!NEXT_CMD.test(command)) return false;
  const normalized = command.replace(/\\/g, "/");
  return normalized.includes(docsAppRoot) || normalized.includes("docs/app");
}

export function isDocsAppNextStart(command, docsAppRoot = getDocsAppRoot()) {
  return isDocsAppNextProcess(command, docsAppRoot) && NEXT_START_CMD.test(command);
}

export function collectAncestorPids() {
  const self = new Set([process.pid]);
  let current = process.ppid;
  for (let depth = 0; depth < 8 && current; depth += 1) {
    self.add(current);
    if (process.platform !== "win32") break;
    try {
      const out = execSync(
        `powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${current}').ParentProcessId"`,
        { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
      ).trim();
      current = out ? Number(out) : 0;
    } catch {
      break;
    }
  }
  return self;
}
