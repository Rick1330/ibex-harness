#!/usr/bin/env node
/** Strip internal prompt/workspace paths from public content. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readMdxParts, walkMdxFiles, writeMdxParts } from "./lib/mdx-walk.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));

const ROOTS = [
  path.resolve(SCRIPT_DIR, "../content/docs"),
  path.resolve(SCRIPT_DIR, "../content/roadmap"),
  path.resolve(SCRIPT_DIR, "../content/blog"),
];

const WORKSPACE_PROMPTS_BACKTICK = "under `ibex-harness-workspace/prompts/`";
const WORKSPACE_PROMPTS_RELOCATED =
  "Execution prompts relocated to the local workspace (`ibex-harness-workspace/prompts/`) — not published";

function stripExecutionPromptSection(body) {
  const heading = "## Execution prompt";
  const start = body.toLowerCase().indexOf(heading.toLowerCase());
  if (start === -1) return body;

  let sectionStart = body.indexOf("\n", start);
  if (sectionStart === -1) return body.slice(0, start).trimEnd();
  sectionStart += 1;

  const endMarkers = ["\n## ", "\n---"];
  let end = body.length;
  for (const marker of endMarkers) {
    const markerIndex = body.indexOf(marker, sectionStart);
    if (markerIndex !== -1 && markerIndex < end) end = markerIndex;
  }

  const head = body.slice(0, start).trimEnd();
  const tail = body.slice(end).trimStart();
  return tail ? `${head}\n${tail}` : head;
}

function normalizeExecutionPromptChecklist(body) {
  return body
    .split("\n")
    .map((line) => {
      const trimmed = line.trimStart().toLowerCase();
      if (trimmed.startsWith("- [x] execution prompt")) {
        return "- [x] Contributor execution materials prepared";
      }
      if (trimmed.startsWith("- [x] add execution prompt")) {
        return "- [x] Contributor execution materials prepared";
      }
      if (trimmed.startsWith("- [x] update") && trimmed.includes("execution prompt")) {
        return "- [x] Contributor documentation updated";
      }
      return line;
    })
    .join("\n");
}

function stripWorkspacePaths(body) {
  return body
    .replace(/`ibex-harness-workspace\/prompts\/[^`]*`/g, "contributor workspace")
    .replace(/ibex-harness-workspace\/prompts\//g, "contributor workspace")
    .replaceAll(WORKSPACE_PROMPTS_BACKTICK, "in the contributor workspace")
    .replace(
      /\| `ibex-harness-workspace\/prompts\/[^|]*` \| [^\n]*/g,
      "| Contributor workspace | Add |",
    )
    .replace(
      /`ibex-harness-workspace\/archive\/foundation\/`/g,
      "contributor workspace archive",
    )
    .replace(/ibex-harness-workspace\/archive\/foundation\//g, "contributor workspace archive");
}

function stripPromptLinks(body) {
  const lines = body.split("\n");
  const filtered = lines.filter((line) => {
    const lower = line.toLowerCase();
    if (lower.includes("](/roadmap/prompts/")) return false;
    if (lower.startsWith("see [milestone-") && lower.includes("(/roadmap/prompts/")) return false;
    return true;
  });

  return filtered
    .join("\n")
    .replaceAll(
      WORKSPACE_PROMPTS_RELOCATED,
      "Execution prompts are not published on the public site.",
    );
}

function sanitizeBody(body) {
  let out = stripExecutionPromptSection(body);
  out = normalizeExecutionPromptChecklist(out);
  out = stripWorkspacePaths(out);
  out = stripPromptLinks(out);
  return collapseBlankLines(out);
}

function collapseBlankLines(text) {
  const lines = text.split("\n");
  const out = [];
  let blankRun = 0;

  for (const line of lines) {
    if (line.trim() === "") {
      blankRun += 1;
      if (blankRun <= 2) out.push("");
      continue;
    }
    blankRun = 0;
    out.push(line);
  }

  return out.join("\n");
}

function sanitizeFrontmatter(fm) {
  return fm
    .replace(/ibex-harness-workspace\/prompts\//g, "contributor workspace")
    .replace(/ibex-harness-workspace\/archive\/foundation\//g, "contributor workspace archive")
    .replace(/`ibex-harness-workspace\/[^`]*`/g, "contributor workspace")
    .replace(/\/roadmap\/prompts\//g, "");
}

function sanitizeMdxFile(abs) {
  const parts = readMdxParts(abs);
  if (!parts) return;
  const fm = sanitizeFrontmatter(parts.fm);
  const body = sanitizeBody(parts.body);
  writeMdxParts(abs, fm, body);
}

for (const root of ROOTS) {
  if (fs.existsSync(root)) walkMdxFiles(root, sanitizeMdxFile);
}

console.log("Sanitized public content (prompt/workspace paths)");
