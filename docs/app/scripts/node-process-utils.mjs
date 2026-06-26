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
  const result = spawnSync(command, args, {
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

function parseCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (const char of line) {
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  values.push(current.trim());
  return values;
}

function parseWmicCsvRows(out, columnNames) {
  const rows = [];
  const headerIndex = new Map();

  for (const line of out.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const values = parseCsvLine(trimmed);
    if (values.length === 0) continue;

    if (headerIndex.size === 0) {
      values.forEach((name, index) => {
        headerIndex.set(name, index);
      });
      continue;
    }

    const record = {};
    for (const name of columnNames) {
      const index = headerIndex.get(name);
      record[name] = index === undefined ? "" : values[index] ?? "";
    }
    rows.push(record);
  }

  return rows;
}

function listWindowsNodeProcesses() {
  const wmicPath = resolveWindowsExecutable("System32", "wbem", "WMIC.exe");
  const out = runCommand(wmicPath, [
    "process",
    "get",
    "ProcessId,CommandLine",
    "/FORMAT:CSV",
  ]);

  return parseWmicCsvRows(out, ["ProcessId", "CommandLine"])
    .map((row) => {
      const pid = safePid(row.ProcessId);
      const command = String(row.CommandLine ?? "");
      if (!pid || !command.toLowerCase().includes("node")) return null;
      return { pid, command };
    })
    .filter(Boolean);
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
  return normalized.includes(docsAppRoot) || normalized.includes("docs/app");
}

export function isDocsAppNextStart(command, docsAppRoot = getDocsAppRoot()) {
  return isDocsAppNextProcess(command, docsAppRoot) && NEXT_START_CMD.test(command);
}

function readWindowsParentPid(pid) {
  const safe = safePid(pid);
  if (!safe) return null;

  const wmicPath = resolveWindowsExecutable("System32", "wbem", "WMIC.exe");
  const out = runCommand(wmicPath, [
    "process",
    "get",
    "ProcessId,ParentProcessId",
    "/FORMAT:CSV",
  ]);

  const match = parseWmicCsvRows(out, ["ProcessId", "ParentProcessId"]).find(
    (row) => safePid(row.ProcessId) === safe,
  );

  return match ? safePid(match.ParentProcessId) : null;
}

function readUnixParentPid(pid) {
  const safe = safePid(pid);
  if (!safe) return null;

  const out = runCommand(UNIX_PS, ["-o", "ppid=", "-p", String(safe)]).trim();
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
