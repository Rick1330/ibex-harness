import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const nextDir = path.join(root, "..", ".next");

if (!fs.existsSync(nextDir)) {
  process.exit(0);
}

fs.rmSync(nextDir, {
  recursive: true,
  force: true,
  maxRetries: 5,
  retryDelay: 200,
});
