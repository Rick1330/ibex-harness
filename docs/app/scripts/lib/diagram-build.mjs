import fs from "node:fs";
import path from "node:path";

export const MERMAID_BLOCK = /```mermaid[ \t]*[^\n]*\n([\s\S]*?)```/g;

export function hashString(input) {
  let hash = 0;
  for (let index = 0; index < input.length; ) {
    const codePoint = input.codePointAt(index) ?? 0;
    hash = Math.trunc(Math.imul(31, hash) + codePoint);
    index += codePoint > 0xffff ? 2 : 1;
  }
  return Math.trunc(Math.abs(hash)).toString(36);
}

export function normalizeMermaidChart(chart) {
  return chart.replaceAll(String.raw`\n`, "\n").trim();
}

export function diagramIdForChart(chart) {
  return `diagram-${hashString(normalizeMermaidChart(chart))}`;
}

function walkMdxFiles(dir, files = []) {
  if (!fs.existsSync(dir)) return files;

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkMdxFiles(fullPath, files);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".mdx")) {
      files.push(fullPath);
    }
  }

  return files;
}

export function collectMermaidCharts(contentRoot) {
  const charts = new Map();

  for (const filePath of walkMdxFiles(contentRoot)) {
    const source = fs.readFileSync(filePath, "utf8");
    for (const match of source.matchAll(MERMAID_BLOCK)) {
      const chart = normalizeMermaidChart(match[1]);
      if (!chart) continue;
      const diagramId = diagramIdForChart(chart);
      if (!charts.has(diagramId)) {
        charts.set(diagramId, chart);
      }
    }
  }

  return charts;
}

export function removeStaleMermaidSources(outDir, charts) {
  if (!fs.existsSync(outDir)) return;

  const expected = new Set([...charts.keys()].map((id) => `${id}.mmd`));
  for (const entry of fs.readdirSync(outDir, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".mmd")) continue;
    if (!expected.has(entry.name)) {
      fs.unlinkSync(path.join(outDir, entry.name));
    }
  }
}
