#!/usr/bin/env node
/**
 * One-time (re-runnable) migration: docs/roadmap/*.md → content/roadmap/*.mdx
 * Excludes prompts/. Rewrites internal prompt paths to workspace location.
 */
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { parseFrontmatterFields } from "./lib/roadmap-parse-fields.mjs";
import {
  buildOrderedPages,
  walkPhaseDir,
  writePhaseMetaFiles,
} from "./lib/roadmap-phase-migrate.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(__dirname, "..");
const LEGACY_ROOT = path.resolve(APP_ROOT, "../roadmap");
const OUTPUT_ROOT = path.resolve(APP_ROOT, "content/roadmap");

const PHASE_ORDER = [
  "phase-0-foundation",
  "phase-1-core-platform",
  "phase-1-5-docs-site",
  "phase-2-single-provider",
  "phase-3-memory-engine",
  "phase-4-multi-provider",
  "phase-5-production-hardening",
];

const ROOT_FILES = {
  "PHASES.md": "overview.mdx",
  "CURRENT_STATE.md": "current-state.mdx",
  "FINDINGS.md": "findings.mdx",
};

const PHASE3_STUB = `

<Callout type="note">
  Milestone definitions for this phase are not published yet. Goals below reflect current planning; detailed milestones will be added in a future update.
</Callout>
`;

function slugify(name) {
  return name
    .replace(/\.md$/i, "")
    .replace(/README/i, "index")
    .replace(/_/g, "-")
    .toLowerCase();
}

function rewriteBody(content) {
  return content
    .replace(/docs\/roadmap\/prompts\//g, "ibex-harness-workspace/prompts/")
    .replace(/\[`docs\/roadmap\/prompts\//g, "[`ibex-harness-workspace/prompts/")
    .replace(/`docs\/roadmap\/prompts\//g, "`ibex-harness-workspace/prompts/");
}

function toMdx(content, fields) {
  const body = rewriteBody(content.trim());
  const fm = ["---"];
  fm.push(`title: ${JSON.stringify(fields.title)}`);
  if (fields.description || fields.summary) {
    fm.push(`description: ${JSON.stringify(fields.summary ?? fields.description ?? "")}`);
  }
  if (fields.summary) fm.push(`summary: ${JSON.stringify(fields.summary)}`);
  if (fields.status) fm.push(`status: ${JSON.stringify(fields.status)}`);
  if (fields.milestoneId) fm.push(`milestoneId: ${JSON.stringify(fields.milestoneId)}`);
  if (fields.goal) fm.push(`goal: ${JSON.stringify(fields.goal)}`);
  if (fields.estimatedEffort) fm.push(`estimatedEffort: ${JSON.stringify(fields.estimatedEffort)}`);
  if (fields.phase) fm.push(`phase: ${JSON.stringify(fields.phase)}`);
  fm.push("---", "", body);
  return fm.join("\n");
}

function writeFile(relPath, content) {
  const full = path.join(OUTPUT_ROOT, relPath);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, "utf8");
}

function cleanOutput() {
  if (fs.existsSync(OUTPUT_ROOT)) {
    fs.rmSync(OUTPUT_ROOT, { recursive: true, force: true });
  }
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
}

function migrateRootFiles() {
  for (const [srcName, destName] of Object.entries(ROOT_FILES)) {
    const src = path.join(LEGACY_ROOT, srcName);
    if (!fs.existsSync(src)) continue;
    const content = fs.readFileSync(src, "utf8");
    const fields = parseFrontmatterFields(content, srcName);
    writeFile(destName, toMdx(content, fields));
  }
}

function migratePhase(phaseDir) {
  const phasePath = path.join(LEGACY_ROOT, phaseDir);
  if (!fs.existsSync(phasePath)) return { pages: [], milestonePages: [] };

  const ctx = {
    phaseDir,
    pages: [],
    milestonePages: [],
    phaseStub: PHASE3_STUB,
    writeFile,
    toMdx,
  };
  walkPhaseDir(ctx, phasePath);

  const goalsPath = path.join(phasePath, "goals.md");
  if (fs.existsSync(goalsPath) && !ctx.pages.includes("goals")) {
    ctx.pages.push("goals");
  }

  const orderedPages = buildOrderedPages(ctx.pages, ctx.milestonePages);
  writePhaseMetaFiles(phaseDir, orderedPages, ctx.milestonePages, writeFile);

  return { pages: orderedPages, milestonePages: ctx.milestonePages };
}

function writeRootMeta() {
  writeFile(
    "meta.json",
    JSON.stringify(
      {
        title: "Roadmap",
        pages: ["overview", "current-state", "findings", "reference", ...PHASE_ORDER],
      },
      null,
      2,
    ) + "\n",
  );
}

function main() {
  if (!fs.existsSync(LEGACY_ROOT)) {
    console.error(`Legacy roadmap not found: ${LEGACY_ROOT}`);
    process.exit(1);
  }

  cleanOutput();
  migrateRootFiles();
  for (const phase of PHASE_ORDER) migratePhase(phase);
  writeRootMeta();

  console.log(`Migrated roadmap content to ${OUTPUT_ROOT}`);
  console.log("Running MDX compatibility fixes...");
  const fix = spawnSync(process.execPath, ["scripts/fix-roadmap-mdx.mjs"], {
    cwd: APP_ROOT,
    stdio: "inherit",
  });
  if (fix.status !== 0) process.exit(fix.status ?? 1);

  const links = spawnSync(process.execPath, ["scripts/fix-roadmap-links.mjs"], {
    cwd: APP_ROOT,
    stdio: "inherit",
  });
  if (links.status !== 0) process.exit(links.status ?? 1);

  const shorten = spawnSync(process.execPath, ["scripts/shorten-sidebar-titles.mjs"], {
    cwd: APP_ROOT,
    stdio: "inherit",
  });
  if (shorten.status !== 0) process.exit(shorten.status ?? 1);

  const sanitize = spawnSync(process.execPath, ["scripts/sanitize-public-content.mjs"], {
    cwd: APP_ROOT,
    stdio: "inherit",
  });
  if (sanitize.status !== 0) process.exit(sanitize.status ?? 1);
}

main();
