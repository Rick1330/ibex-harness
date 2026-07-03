import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DEFAULT_DIST, FALLBACK_DIST, tryQuarantineStaleNext } from "./resolve-dist-dir.mjs";

const root = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.join(root, "..");

function removeDist(distDirName) {
  const nextDir = path.join(appRoot, distDirName);
  if (!fs.existsSync(nextDir)) {
    return;
  }

  try {
    fs.rmSync(nextDir, {
      recursive: true,
      force: true,
      maxRetries: 5,
      retryDelay: 200,
    });
  } catch (error) {
    if (error.code === "EPERM" || error.code === "EACCES") {
      if (!tryQuarantineStaleNext(distDirName)) {
        console.warn(
          `[clean-next] Could not remove or quarantine ${distDirName}; dev will use ${FALLBACK_DIST} if needed.`,
        );
      }
      return;
    }
    throw error;
  }
}

removeDist(DEFAULT_DIST);
removeDist(FALLBACK_DIST);
