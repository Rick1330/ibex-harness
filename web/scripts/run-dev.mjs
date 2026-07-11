import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";

import { appRoot, resolveDistDir } from "./resolve-dist-dir.mjs";

const require = createRequire(import.meta.url);
const nextBin = path.join(
  path.dirname(require.resolve("next/package.json")),
  "dist/bin/next",
);
const distDir = resolveDistDir();
const extraArgs = process.argv.slice(2);

const child = spawn(process.execPath, [nextBin, "dev", ...extraArgs], {
  cwd: appRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    NEXT_DIST_DIR: distDir,
  },
});

child.on("error", (error) => {
  console.error(`[dev] Failed to start Next.js dev server: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
