import fs from "node:fs";
import path from "node:path";

import themeTokens from "../../src/lib/mermaid-theme-tokens.json" with { type: "json" };

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

function palette(isDark) {
  return isDark ? themeTokens.dark : themeTokens.light;
}

function buildThemeCss(isDark) {
  const {
    text,
    nodeFill,
    nodeStroke,
    line,
    edgeLabelBg,
    edgeLabelText,
    clusterFill,
  } = palette(isDark);

  return `
    .node rect, .node circle, .node polygon, .node path:not(.flowchart-link) {
      fill: ${nodeFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .cluster rect {
      fill: ${clusterFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .edgePath path, .flowchart-link, .edgePaths path {
      stroke: ${line} !important;
    }
    marker path, #arrowhead path {
      fill: ${line} !important;
      stroke: ${line} !important;
    }
    text, tspan, .label, .nodeLabel, .edgeLabel, .entityLabel, .relationshipLabel {
      fill: ${text} !important;
    }
    .edgeLabel rect {
      fill: ${edgeLabelBg} !important;
      stroke: ${nodeStroke} !important;
    }
    .edgeLabel text, .edgeLabel tspan {
      fill: ${edgeLabelText} !important;
    }
    .actor, .actor-line, .messageLine0, .messageLine1 {
      stroke: ${line} !important;
    }
    .actor rect, .actor path, .entityBox, .attributeBoxOdd, .attributeBoxEven {
      fill: ${nodeFill} !important;
      stroke: ${nodeStroke} !important;
    }
    .messageText0, .messageText1, .loopText, .loopText tspan {
      fill: ${text} !important;
    }
    .relationshipLine {
      stroke: ${line} !important;
    }
    foreignObject div, foreignObject span, foreignObject p {
      color: ${text} !important;
    }
    foreignObject .labelBkg, .labelBkg {
      background-color: ${edgeLabelBg} !important;
    }
  `.trim();
}

/** Post-process Mermaid SVG for readable labels across diagram types. */
export function applyMermaidSvgTheme(svg, isDark) {
  const { text } = palette(isDark);
  const css = buildThemeCss(isDark);

  let result = svg.replace(
    /<svg([^>]*)>/i,
    `<svg$1><style type="text/css">${css}</style>`,
  );

  result = result.replace(/<text\b([^>]*?)>/gi, (_full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<text${cleaned} fill="${text}">`;
  });

  result = result.replace(/<tspan\b([^>]*?)>/gi, (_full, attrs) => {
    const cleaned = String(attrs).replace(/\sfill="[^"]*"/gi, "");
    return `<tspan${cleaned} fill="${text}">`;
  });

  return result;
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
