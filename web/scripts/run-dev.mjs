import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";

import { appRoot, resolveDistDir } from "./resolve-dist-dir.mjs";
import { resolveNodeHeapMb } from "./node-heap.mjs";

const require = createRequire(import.meta.url);
const nextBin = path.join(
  path.dirname(require.resolve("next/package.json")),
  "dist/bin/next",
);
const distDir = resolveDistDir();
const extraArgs = process.argv.slice(2);
const wantsTurbo =
  extraArgs.includes("--turbopack") || extraArgs.includes("--turbo");

const devArgs = ["dev"];
// Turbopack's native lockfile binding is unreliable on Windows (Next 16.2.x).
if (
  process.platform === "win32" &&
  !wantsTurbo &&
  process.env.NEXT_USE_TURBOPACK !== "1"
) {
  devArgs.push("--webpack");
}

/**
 * Heap for the *main* Next process only (via node argv).
 *
 * Do NOT put `--max-old-space-size` in NODE_OPTIONS: jest-workers inherit it,
 * each reserves that much address space, and Windows OOMs compiling heavy
 * routes like /roadmap/[...slug] ("Zone Allocation failed").
 */
const heapMb = resolveNodeHeapMb(process.env.IBEX_NODE_HEAP_MB);
const strippedNodeOptions = (process.env.NODE_OPTIONS ?? "")
  .split(/\s+/)
  .filter(Boolean)
  .filter(
    (flag) =>
      !flag.includes("max-old-space-size") &&
      !flag.includes("max_old_space_size"),
  )
  .join(" ");

const child = spawn(
  process.execPath,
  [`--max-old-space-size=${heapMb}`, nextBin, ...devArgs, ...extraArgs],
  {
    cwd: appRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      NODE_OPTIONS: strippedNodeOptions,
      NEXT_DIST_DIR: distDir,
      // Keep compile workers lean on Windows (roadmap MDX + large CSS).
      ...(process.platform === "win32"
        ? { UV_THREADPOOL_SIZE: "2" }
        : {}),
    },
  },
);

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
