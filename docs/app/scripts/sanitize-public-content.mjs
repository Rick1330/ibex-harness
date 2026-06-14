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
  return body.replace(
    /## Execution prompt\s*\n[\s\S]*?(?=\n## |\n---\s*\n|$)/gi,
    "",
  );
}

function normalizeExecutionPromptChecklist(body) {
  return body
    .replace(/- \[x\] Execution prompt[^\n]*/gi, "- [x] Contributor execution materials prepared")
    .replace(/- \[x\] Add execution prompt[^\n]*/gi, "- [x] Contributor execution materials prepared")
    .replace(
      /- \[x\] Update[^\n]*execution prompt[^\n]*/gi,
      "- [x] Contributor documentation updated",
    );
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
  return body
    .replace(/\[([^\]]*)\]\(\/roadmap\/prompts\/[^)]+\)/g, "")
    .replace(/See \[MILESTONE-[^\]]+\]\(\/roadmap\/prompts\/[^)]+\)\.?/g, "")
    .replace(
      WORKSPACE_PROMPTS_RELOCATED,
      "Execution prompts are not published on the public site.",
    );
}

function sanitizeBody(body) {
  let out = stripExecutionPromptSection(body);
  out = normalizeExecutionPromptChecklist(out);
  out = stripWorkspacePaths(out);
  out = stripPromptLinks(out);
  return out.replace(/\n{3,}/g, "\n\n");
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
