/**
 * Prerender Mermaid diagrams to public/diagrams/ at build time.
 * Requires @mermaid-js/mermaid-cli (mmdc). On Windows, uses system Chrome when
 * available; set PUPPETEER_EXECUTABLE_PATH if mmdc cannot find a browser.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  collectMermaidCharts,
} from "./lib/diagram-build.mjs";
import { applyMermaidSvgTheme } from "./lib/mermaid-theme-css.mjs";
import { mmdcFailureMessage, runMmdc } from "./lib/run-mmdc.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contentRoot = path.join(appRoot, "content");
const outDir = path.join(appRoot, "public", "diagrams");
const mmdcConfigPath = path.join(appRoot, "scripts", "mermaid-mmdc-config.json");
const puppeteerConfigPath = path.join(appRoot, "scripts", "puppeteer-config.json");

function resolveChromeExecutable() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) {
    return process.env.PUPPETEER_EXECUTABLE_PATH;
  }

  const candidates = [
    path.join(
      process.env.ProgramFiles ?? "C:\\Program Files",
      "Google",
      "Chrome",
      "Application",
      "chrome.exe",
    ),
    path.join(
      process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)",
      "Google",
      "Chrome",
      "Application",
      "chrome.exe",
    ),
    path.join(
      process.env.LOCALAPPDATA ?? "",
      "Google",
      "Chrome",
      "Application",
      "chrome.exe",
    ),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }

  return null;
}

function buildMmdcArgs(inputPath, outputPath) {
  const args = [
    "-i",
    inputPath,
    "-o",
    outputPath,
    "-b",
    "transparent",
    "-c",
    mmdcConfigPath,
  ];

  if (process.env.CI || process.env.GITHUB_ACTIONS) {
    args.push("-p", puppeteerConfigPath);
  }

  return args;
}

function renderBaseSvg(chart) {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ibex-mermaid-"));
  const inputPath = path.join(tmpDir, "chart.mmd");
  const outputPath = path.join(tmpDir, "chart.svg");
  const chromePath = resolveChromeExecutable();

  try {
    fs.writeFileSync(inputPath, chart, "utf8");
    const env = { ...process.env };
    if (chromePath) {
      env.PUPPETEER_EXECUTABLE_PATH = chromePath;
    }

    const result = runMmdc(appRoot, buildMmdcArgs(inputPath, outputPath), env);

    if (result.status !== 0) {
      throw new Error(mmdcFailureMessage(result, chromePath));
    }

    if (!fs.existsSync(outputPath)) {
      throw new Error("mmdc did not produce an SVG file");
    }

    return fs.readFileSync(outputPath, "utf8");
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

const charts = collectMermaidCharts(contentRoot);
let rendered = 0;

for (const [diagramId, chart] of charts) {
  fs.writeFileSync(path.join(outDir, `${diagramId}.mmd`), chart, "utf8");
  const baseSvg = renderBaseSvg(chart);
  for (const theme of ["light", "dark"]) {
    const isDark = theme === "dark";
    const svg = applyMermaidSvgTheme(baseSvg, isDark);
    fs.writeFileSync(path.join(outDir, `${diagramId}-${theme}.svg`), svg, "utf8");
    rendered += 1;
  }
}

const manifest = Object.fromEntries(
  [...charts.keys()].map((diagramId) => [diagramId, { light: true, dark: true }]),
);
fs.writeFileSync(
  path.join(outDir, "manifest.json"),
  JSON.stringify(manifest, null, 2),
  "utf8",
);

console.log(`Prerendered ${rendered} diagram SVGs (${charts.size} unique charts).`);
