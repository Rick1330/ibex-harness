import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const NEXT_CMD = /\bnext\s+(dev|build|start)\b/i;
const NEXT_START_CMD = /\bnext\s+start\b/i;
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DOCS_APP_ROOT = path.resolve(SCRIPT_DIR, "..");

function safePid(value) {
  const pid = Number(value);
  if (!Number.isInteger(pid) || pid <= 0) {
    return null;
  }
  return pid;
}

export function getDocsAppRoot() {
  return DOCS_APP_ROOT.replace(/\\/g, "/");
}

function runCommand(command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.error || result.status !== 0) {
    return "";
  }
  return result.stdout ?? "";
}

export function listNodeProcesses() {
  if (process.platform !== "win32") {
    const out = runCommand("ps", ["-ax", "-o", "pid=,command="]);
    if (!out) return [];

    return out
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const match = line.match(/^(\d+)\s+(.*)$/);
        if (!match) return null;
        const pid = safePid(match[1]);
        if (!pid) return null;
        return { pid, command: match[2] };
      })
      .filter(Boolean);
  }

  const out = runCommand("powershell", [
    "-NoProfile",
    "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
  ]).trim();
  if (!out) return [];

  try {
    const parsed = JSON.parse(out);
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    return rows
      .map((row) => {
        const pid = safePid(row?.ProcessId);
        if (!pid || !row?.CommandLine) return null;
        return { pid, command: String(row.CommandLine) };
      })
      .filter(Boolean);
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

function readWindowsParentPid(pid) {
  const out = runCommand("powershell", [
    "-NoProfile",
    "-Command",
    `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').ParentProcessId`,
  ]).trim();
  return safePid(out);
}

function readUnixParentPid(pid) {
  const out = runCommand("ps", ["-o", "ppid=", "-p", String(pid)]).trim();
  return safePid(out);
}

export function collectAncestorPids() {
  const self = new Set([process.pid]);
  let current = safePid(process.ppid);

  for (let depth = 0; depth < 8 && current; depth += 1) {
    self.add(current);
    current =
      process.platform === "win32"
        ? readWindowsParentPid(current)
        : readUnixParentPid(current);
  }

  return self;
}
