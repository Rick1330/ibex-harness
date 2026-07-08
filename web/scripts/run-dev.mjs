import { spawn } from "node:child_process";
import path from "node:path";

import { appRoot, resolveDistDir } from "./resolve-dist-dir.mjs";

const distDir = resolveDistDir();
const nextBin = path.join(appRoot, "node_modules", "next", "dist", "bin", "next");
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
