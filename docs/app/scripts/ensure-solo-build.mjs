import process from "node:process";

import {
  collectAncestorPids,
  isDocsAppNextProcess,
  listNodeProcesses,
} from "./node-process-utils.mjs";

const selfPids = collectAncestorPids();
const conflicts = listNodeProcesses().filter(
  (entry) =>
    !selfPids.has(entry.pid) && isDocsAppNextProcess(entry.command),
);

if (conflicts.length === 0) {
  process.exit(0);
}

console.warn(
  "\n[build] Found other Next.js processes for docs/app (can cause Windows ENOTEMPTY / silent hangs):",
);
for (const entry of conflicts) {
  console.warn(`  - pid ${entry.pid}`);
}
console.warn(
  "  Stop them first: Ctrl+C in those terminals, or run `pnpm stop:next` from docs/app.\n",
);

if (process.argv.includes("--strict")) {
  process.exit(1);
}
