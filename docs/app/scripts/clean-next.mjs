import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nextDir = path.join(appRoot, ".next");

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function removeNextDir(retries = 8) {
  if (!fs.existsSync(nextDir)) {
    return;
  }

  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      fs.rmSync(nextDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
      return;
    } catch (error) {
      const code = error && typeof error === "object" ? error.code : undefined;
      const retryable = code === "EPERM" || code === "EBUSY" || code === "ENOTEMPTY";
      if (!retryable || attempt === retries) {
        throw error;
      }
      await sleep(250 * attempt);
    }
  }
}

await removeNextDir();
console.log("Removed .next");
