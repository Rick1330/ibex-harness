/**
 * Prerender Mermaid diagrams to public/diagrams/ at build time.
 * Requires @mermaid-js/mermaid-cli (mmdc). On Windows, uses system Chrome when
 * available; set PUPPETEER_EXECUTABLE_PATH if mmdc cannot find a browser.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  applyMermaidSvgTheme,
  collectMermaidCharts,
} from "./lib/diagram-build.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contentRoot = path.join(appRoot, "content");
const outDir = path.join(appRoot, "public", "diagrams");
const mmdcConfigPath = path.join(appRoot, "scripts", "mermaid-mmdc-config.json");

function resolveMmdcBinary() {
  const binName = process.platform === "win32" ? "mmdc.cmd" : "mmdc";
  const localBin = path.join(appRoot, "node_modules", ".bin", binName);
  if (fs.existsSync(localBin)) return localBin;

  const rootBin = path.join(
    appRoot,
    "..",
    "..",
    "node_modules",
    ".bin",
    binName,
  );
  if (fs.existsSync(rootBin)) return rootBin;

  throw new Error(
    "mmdc not found. Install @mermaid-js/mermaid-cli in docs/app devDependencies.",
  );
}

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

function renderBaseSvg(chart) {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "ibex-mermaid-"));
  const inputPath = path.join(tmpDir, "chart.mmd");
  const outputPath = path.join(tmpDir, "chart.svg");
  const chromePath = resolveChromeExecutable();

  try {
    fs.writeFileSync(inputPath, chart, "utf8");
    const mmdc = resolveMmdcBinary();
    const env = { ...process.env };
    if (chromePath) {
      env.PUPPETEER_EXECUTABLE_PATH = chromePath;
    }

    const result = spawnSync(
      mmdc,
      [
        "-i",
        inputPath,
        "-o",
        outputPath,
        "-b",
        "transparent",
        "-c",
        mmdcConfigPath,
      ],
      {
        cwd: appRoot,
        encoding: "utf8",
        env,
        shell: process.platform === "win32",
      },
    );

    if (result.status !== 0) {
      const detail = [result.stderr, result.stdout].filter(Boolean).join("\n");
      const hint = chromePath
        ? ""
        : "\nHint: set PUPPETEER_EXECUTABLE_PATH to your Chrome/Chromium binary.";
      throw new Error(
        detail || `mmdc exited with code ${result.status ?? "unknown"}${hint}`,
      );
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
