import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const NEXT_CMD = /\bnext\s+(dev|build|start)\b/i;
const NEXT_START_CMD = /\bnext\s+start\b/i;
const UNIX_PS = "/bin/ps";
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DOCS_APP_ROOT = path.resolve(SCRIPT_DIR, "..");

function safePid(value) {
  const pid = Number(value);
  if (!Number.isInteger(pid) || pid <= 0) {
    return null;
  }
  return pid;
}

function resolveWindowsExecutable(...segments) {
  const systemRoot = process.env.SystemRoot ?? String.raw`C:\Windows`;
  return path.join(systemRoot, ...segments);
}

function runCommand(command, args) {
  const result = spawnSync(command, args, { // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process
    encoding: "utf8",
    shell: false,
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.error || result.status !== 0) {
    return "";
  }
  return result.stdout ?? "";
}

function parseUnixProcessLine(line) {
  const spaceIndex = line.indexOf(" ");
  if (spaceIndex <= 0) return null;

  const pid = safePid(line.slice(0, spaceIndex));
  if (!pid) return null;

  return { pid, command: line.slice(spaceIndex + 1).trim() };
}

function listUnixNodeProcesses() {
  const out = runCommand(UNIX_PS, ["-ax", "-o", "pid=,command="]);
  if (!out) return [];

  return out
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map(parseUnixProcessLine)
    .filter(Boolean);
}

function parseWmicListRecords(out, keys) {
  const records = [];
  let current = {};

  for (const line of out.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (Object.keys(current).length > 0) {
        records.push(current);
      }
      current = {};
      continue;
    }

    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;

    const key = trimmed.slice(0, separator);
    if (!keys.includes(key)) continue;

    current[key] = trimmed.slice(separator + 1);
  }

  if (Object.keys(current).length > 0) {
    records.push(current);
  }

  return records;
}

function listWindowsNodeProcesses() {
  const wmicPath = resolveWindowsExecutable("System32", "wbem", "WMIC.exe");
  const out = runCommand(wmicPath, [
    "process",
    "where",
    "name='node.exe'",
    "get",
    "ProcessId,CommandLine",
    "/format:list",
  ]);

  return parseWmicListRecords(out, ["ProcessId", "CommandLine"])
    .map((record) => {
      const pid = safePid(record.ProcessId);
      const command =
        typeof record.CommandLine === "string" ? record.CommandLine : "";
      if (!pid || !command) return null;
      return { pid, command };
    })
    .filter(Boolean);
}

function readWindowsParentByPid() {
  const wmicPath = resolveWindowsExecutable("System32", "wbem", "WMIC.exe");
  const out = runCommand(wmicPath, [
    "process",
    "get",
    "ProcessId,ParentProcessId",
    "/format:list",
  ]);
  const parentByPid = new Map();

  for (const record of parseWmicListRecords(out, [
    "ProcessId",
    "ParentProcessId",
  ])) {
    const pid = safePid(record.ProcessId);
    const parentPid = safePid(record.ParentProcessId);
    if (!pid || !parentPid) continue;
    parentByPid.set(pid, parentPid);
  }

  return parentByPid;
}

export function getDocsAppRoot() {
  return DOCS_APP_ROOT.replaceAll("\\", "/");
}

export function listNodeProcesses() {
  if (process.platform === "win32") {
    return listWindowsNodeProcesses();
  }
  return listUnixNodeProcesses();
}

export function isDocsAppNextProcess(command, docsAppRoot = getDocsAppRoot()) {
  if (!NEXT_CMD.test(command)) return false;
  const normalized = command.replaceAll("\\", "/");
  return normalized.includes(docsAppRoot) || normalized.includes("web");
}

export function isDocsAppNextStart(command, docsAppRoot = getDocsAppRoot()) {
  return isDocsAppNextProcess(command, docsAppRoot) && NEXT_START_CMD.test(command);
}

function readUnixParentPid(pid) {
  const safe = safePid(pid);
  if (!safe) return null;

  const out = runCommand(UNIX_PS, ["-o", "ppid=", "-p", String(safe)]).trim();
  return safePid(out);
}

export function collectAncestorPids() {
  const self = new Set([process.pid]);
  const windowsParents =
    process.platform === "win32" ? readWindowsParentByPid() : null;
  let current = safePid(process.ppid);

  for (let depth = 0; depth < 8 && current; depth += 1) {
    self.add(current);
    current =
      windowsParents === null
        ? readUnixParentPid(current)
        : (windowsParents.get(current) ?? null);
  }

  return self;
}
