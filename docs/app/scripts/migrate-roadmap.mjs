#!/usr/bin/env node
/**
 * One-time (re-runnable) migration: docs/roadmap/*.md → content/roadmap/*.mdx
 * Excludes prompts/. Rewrites internal prompt paths to workspace location.
 */
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

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

function parseStatus(raw) {
  const value = raw.trim().toLowerCase();
  if (value.includes("complete")) return "completed";
  if (value.includes("progress")) return "in-progress";
  if (value.includes("planned")) return "planned";
  return undefined;
}

function parseFrontmatterFields(content, filePath) {
  const titleMatch = content.match(/^#\s+(.+)$/m);
  const title = titleMatch?.[1]?.trim() ?? path.basename(filePath, ".md");

  const statusMatch = content.match(/\*\*Status:\*\*\s*(.+)/i);
  const status = statusMatch ? parseStatus(statusMatch[1]) : undefined;

  const effortMatch = content.match(/\*\*Estimated effort:\*\*\s*(.+)/i);
  const estimatedEffort = effortMatch?.[1]?.trim();

  const goalMatch = content.match(/\*\*Goal:\*\*\s*(.+)/i);
  const goal = goalMatch?.[1]?.trim();

  let milestoneId;
  const base = path.basename(filePath, ".md");
  const idMatch = base.match(/^(\d+\.\d+\.\d+|d\d+\.\d+)/i);
  if (idMatch) milestoneId = idMatch[1].toLowerCase();

  let summary;
  const whySection = content.match(
    /## Why This Milestone Exists\s*\n+([\s\S]*?)(?=\n## |\n---|\n$)/i,
  );
  if (whySection) {
    summary = whySection[1]
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 2)
      .join(" ")
      .replace(/\[(.+?)\]\(.+?\)/g, "$1")
      .slice(0, 320);
  } else {
    const firstPara = content
      .replace(/^---[\s\S]*?---\n/m, "")
      .replace(/^#.+$/m, "")
      .split("\n\n")
      .map((p) => p.trim())
      .find((p) => p && !p.startsWith("#") && !p.startsWith("|") && !p.startsWith("```"));
    summary = firstPara?.replace(/\[(.+?)\]\(.+?\)/g, "$1").slice(0, 320);
  }

  const phaseMatch = filePath.match(/phase-[^/\\]+/);
  const phase = phaseMatch?.[0];

  return { title, status, estimatedEffort, goal, milestoneId, summary, phase };
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

function resolveDestName(phaseDir, entry, rel, relPath) {
  if (entry.name === "README.md") {
    return rel ? `${rel}/index.mdx` : `${phaseDir}/index.mdx`;
  }
  return `${phaseDir}/${relPath.replace(/\.md$/i, ".mdx")}`;
}

function shouldAppendPhaseStub(phaseDir, rel) {
  return (
    rel === "" &&
    ["phase-3-memory-engine", "phase-4-multi-provider", "phase-5-production-hardening"].includes(
      phaseDir,
    )
  );
}

function trackMigratedPage(destName, phaseDir, rel, pages, milestonePages) {
  const slug = destName
    .replace(`${phaseDir}/`, "")
    .replace(/\.mdx$/, "")
    .replace(/\\/g, "/");

  if (destName.includes("/milestones/")) {
    milestonePages.push(slug);
    return;
  }

  if (!destName.endsWith("/index.mdx") || rel === "") {
    pages.push(slug === "index" ? "index" : slug.replace(/\/index$/, "") || slug);
  }
}

function walkPhaseDir(ctx, dir, rel = "") {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "prompts") continue;
    const abs = path.join(dir, entry.name);
    const relPath = rel ? `${rel}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      walkPhaseDir(ctx, abs, relPath);
      continue;
    }

    if (!entry.name.endsWith(".md")) continue;

    let content = fs.readFileSync(abs, "utf8");
    const fields = parseFrontmatterFields(content, abs);
    const destName = resolveDestName(ctx.phaseDir, entry, rel, relPath);

    if (entry.name === "README.md" && shouldAppendPhaseStub(ctx.phaseDir, rel)) {
      content = `${content.trim()}${PHASE3_STUB}`;
    }

    writeFile(destName, toMdx(content, fields));
    trackMigratedPage(destName, ctx.phaseDir, rel, ctx.pages, ctx.milestonePages);
  }
}

function migratePhase(phaseDir) {
  const phasePath = path.join(LEGACY_ROOT, phaseDir);
  if (!fs.existsSync(phasePath)) return { pages: [], milestonePages: [] };

  const ctx = { phaseDir, pages: [], milestonePages: [] };
  walkPhaseDir(ctx, phasePath);
  const { pages, milestonePages } = ctx;

  // goals.mdx for phase 3-5 if exists
  const goalsPath = path.join(phasePath, "goals.md");
  if (fs.existsSync(goalsPath) && !pages.includes("goals")) {
    pages.push("goals");
  }

  // Build ordered pages for meta.json
  const orderedPages = [];
  if (pages.includes("index")) orderedPages.push("index");
  for (const p of ["goals", "decisions", "risks"]) {
    if (pages.includes(p)) orderedPages.push(p);
  }
  for (const p of pages) {
    if (!orderedPages.includes(p) && p !== "index" && !p.startsWith("milestones")) {
      orderedPages.push(p);
    }
  }
  if (milestonePages.length > 0) orderedPages.push("milestones");

  milestonePages.sort();

  if (milestonePages.length > 0) {
    writeFile(
      `${phaseDir}/milestones/meta.json`,
      JSON.stringify(
        {
          title: "Milestones",
          pages: milestonePages.map((p) => p.replace(/^milestones\//, "")),
        },
        null,
        2,
      ) + "\n",
    );
  }

  writeFile(
    `${phaseDir}/meta.json`,
    JSON.stringify({ title: phaseDir.replace(/-/g, " "), pages: orderedPages }, null, 2) + "\n",
  );

  return { pages: orderedPages, milestonePages };
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
