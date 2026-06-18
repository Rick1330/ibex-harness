import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { collectMermaidCharts } from "./lib/diagram-build.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contentRoot = path.join(appRoot, "content");
const outDir = path.join(appRoot, "public", "diagrams");
const manifestPath = path.join(outDir, "manifest.json");

const charts = collectMermaidCharts(contentRoot);
const errors = [];

for (const diagramId of charts.keys()) {
  const mmdPath = path.join(outDir, `${diagramId}.mmd`);
  const lightPath = path.join(outDir, `${diagramId}-light.svg`);
  const darkPath = path.join(outDir, `${diagramId}-dark.svg`);

  if (!fs.existsSync(mmdPath)) {
    errors.push(`missing ${diagramId}.mmd`);
  }
  if (!fs.existsSync(lightPath)) {
    errors.push(`missing ${diagramId}-light.svg`);
  }
  if (!fs.existsSync(darkPath)) {
    errors.push(`missing ${diagramId}-dark.svg`);
  }
}

if (fs.existsSync(manifestPath)) {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  for (const diagramId of charts.keys()) {
    if (!manifest[diagramId]) {
      errors.push(`manifest missing entry for ${diagramId}`);
    }
  }
  for (const diagramId of Object.keys(manifest)) {
    if (!charts.has(diagramId)) {
      errors.push(`stale manifest entry for ${diagramId}`);
    }
  }
} else if (charts.size > 0) {
  errors.push("missing manifest.json — run prerender-mermaid.mjs");
}

if (errors.length > 0) {
  console.error("Diagram asset verification failed:\n");
  for (const error of errors) {
    console.error(`  - ${error}`);
  }
  console.error(
    "\nRun: pnpm --filter docs exec node ./scripts/prerender-mermaid.mjs",
  );
  process.exit(1);
}

console.log(`Verified ${charts.size} diagram asset(s).`);
