import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  collectMermaidCharts,
  removeStaleMermaidSources,
} from "./lib/diagram-build.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contentRoot = path.join(appRoot, "content");
const outDir = path.join(appRoot, "public", "diagrams");

fs.mkdirSync(outDir, { recursive: true });

const charts = collectMermaidCharts(contentRoot);
removeStaleMermaidSources(outDir, charts);

for (const [diagramId, chart] of charts) {
  fs.writeFileSync(path.join(outDir, `${diagramId}.mmd`), chart, "utf8");
}

console.log(`Exported ${charts.size} mermaid source files to public/diagrams/`);
