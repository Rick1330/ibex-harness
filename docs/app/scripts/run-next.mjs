import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const cleanScript = path.join(appRoot, "scripts", "clean-next.mjs");
const nextBin = path.join(
  appRoot,
  "node_modules",
  "next",
  "dist",
  "bin",
  "next",
);

const [mode, ...extraArgs] = process.argv.slice(2);
if (!mode || !["dev", "build", "start"].includes(mode)) {
  console.error("Usage: node scripts/run-next.mjs <dev|build|start> [next args...]");
  process.exit(1);
}

const clean = spawnSync(process.execPath, [cleanScript], {
  cwd: appRoot,
  stdio: "inherit",
  shell: false,
});
if (clean.status !== 0) {
  process.exit(clean.status ?? 1);
}

if (mode === "build") {
  const prebuildScripts = [
    path.join(appRoot, "scripts", "export-page-markdown.mjs"),
    path.join(appRoot, "scripts", "prerender-mermaid.mjs"),
    path.join(appRoot, "scripts", "verify-diagram-assets.mjs"),
  ];
  for (const script of prebuildScripts) {
    const pre = spawnSync(process.execPath, [script], {
      cwd: appRoot,
      stdio: "inherit",
      shell: false,
    });
    if (pre.status !== 0) {
      process.exit(pre.status ?? 1);
    }
  }
}

const nextArgs = [mode, ...extraArgs];
const run = spawnSync(process.execPath, [nextBin, ...nextArgs], {
  cwd: appRoot,
  stdio: "inherit",
  shell: false,
});

process.exit(run.status ?? 1);
