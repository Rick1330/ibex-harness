import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
export const appRoot = path.join(scriptDir, "..");
export const harnessRoot = path.join(appRoot, "..", "..");

export const DEFAULT_DIST = ".next";
export const FALLBACK_DIST = ".next-dev";

function distPath(distDirName) {
  return path.join(appRoot, distDirName);
}

export function isTraceWritable(distDirName) {
  const nextDir = distPath(distDirName);
  const tracePath = path.join(nextDir, "trace");
  try {
    fs.mkdirSync(nextDir, { recursive: true });
    const handle = fs.openSync(tracePath, "a");
    fs.closeSync(handle);
    return true;
  } catch (error) {
    if (error.code === "EPERM" || error.code === "EACCES") {
      return false;
    }
    throw error;
  }
}

export function tryQuarantineStaleNext(distDirName = DEFAULT_DIST) {
  const nextDir = distPath(distDirName);
  if (!fs.existsSync(nextDir)) {
    return true;
  }

  const quarantineName = `${distDirName}.stale-${Date.now()}`;
  const quarantinePath = distPath(quarantineName);
  try {
    fs.renameSync(nextDir, quarantinePath);
    console.warn(`[dev] Quarantined locked ${distDirName} → ${quarantineName}`);
    return true;
  } catch (error) {
    if (error.code !== "EPERM" && error.code !== "EACCES") {
      throw error;
    }
    return false;
  }
}

export function resolveDistDir() {
  const override = process.env.NEXT_DIST_DIR?.trim();
  if (override) {
    return override;
  }

  if (isTraceWritable(DEFAULT_DIST)) {
    return DEFAULT_DIST;
  }

  if (tryQuarantineStaleNext(DEFAULT_DIST) && isTraceWritable(DEFAULT_DIST)) {
    return DEFAULT_DIST;
  }

  if (isTraceWritable(FALLBACK_DIST)) {
    console.warn(
      `[dev] ${DEFAULT_DIST}/trace is locked on Windows; using ${FALLBACK_DIST} for this session.`,
    );
    return FALLBACK_DIST;
  }

  tryQuarantineStaleNext(FALLBACK_DIST);
  return FALLBACK_DIST;
}
