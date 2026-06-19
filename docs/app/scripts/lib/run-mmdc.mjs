/**
 * Spawn mmdc without shell (Sonar-safe). Uses Node to run the CLI entry directly.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

function resolveMmdcCliJs(appRoot) {
  const candidates = [
    path.join(appRoot, "node_modules", "@mermaid-js", "mermaid-cli", "src", "cli.js"),
    path.join(appRoot, "..", "..", "node_modules", "@mermaid-js", "mermaid-cli", "src", "cli.js"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  throw new Error(
    "mmdc not found. Install @mermaid-js/mermaid-cli in docs/app devDependencies.",
  );
}

export function runMmdc(appRoot, mmdcArgs, env) {
  const cliJs = resolveMmdcCliJs(appRoot);
  return spawnSync(process.execPath, [cliJs, ...mmdcArgs], {
    cwd: appRoot,
    encoding: "utf8",
    env,
    shell: false,
    windowsHide: true,
  });
}

export function mmdcFailureMessage(result, chromePath) {
  const detail = [result.stderr, result.stdout].filter(Boolean).join("\n");
  const hint = chromePath
    ? ""
    : "\nHint: set PUPPETEER_EXECUTABLE_PATH to your Chrome/Chromium binary.";
  return detail || `mmdc exited with code ${result.status ?? "unknown"}${hint}`;
}
