import fs from "node:fs";
import path from "node:path";

import { parseFrontmatterFields } from "./roadmap-parse-fields.mjs";

const PHASE_PAGE_PREFIX = ["index", "goals", "decisions", "risks"];

export function resolveDestName(phaseDir, entry, rel, relPath) {
  if (entry.name === "README.md") {
    return rel ? `${rel}/index.mdx` : `${phaseDir}/index.mdx`;
  }
  return `${phaseDir}/${relPath.replace(/\.md$/i, ".mdx")}`;
}

export function shouldAppendPhaseStub(phaseDir, rel) {
  return (
    rel === "" &&
    ["phase-3-memory-engine", "phase-4-multi-provider", "phase-5-production-hardening"].includes(
      phaseDir,
    )
  );
}

export function trackMigratedPage(ctx, destName, rel) {
  const { phaseDir, pages, milestonePages } = ctx;
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

export function processMarkdownEntry(ctx, entryDescriptor) {
  const { entry, abs, rel, relPath } = entryDescriptor;
  let content = fs.readFileSync(abs, "utf8");
  const fields = parseFrontmatterFields(content, abs);
  const destName = resolveDestName(ctx.phaseDir, entry, rel, relPath);

  if (entry.name === "README.md" && shouldAppendPhaseStub(ctx.phaseDir, rel)) {
    content = `${content.trim()}${ctx.phaseStub}`;
  }

  ctx.writeFile(destName, ctx.toMdx(content, fields));
  trackMigratedPage(ctx, destName, rel);
}

export function walkPhaseDir(ctx, dir, rel = "") {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "prompts") continue;
    const abs = path.join(dir, entry.name);
    const relPath = rel ? `${rel}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      walkPhaseDir(ctx, abs, relPath);
      continue;
    }

    if (!entry.name.endsWith(".md")) continue;
    processMarkdownEntry(ctx, { entry, abs, rel, relPath });
  }
}

function appendUniquePages(target, pages, skip) {
  for (const page of pages) {
    if (skip.has(page)) continue;
    target.push(page);
    skip.add(page);
  }
}

export function buildOrderedPages(pages, milestonePages) {
  const skip = new Set(PHASE_PAGE_PREFIX);
  const ordered = PHASE_PAGE_PREFIX.filter((page) => pages.includes(page));
  const remainder = pages.filter((page) => !skip.has(page) && !page.startsWith("milestones"));
  appendUniquePages(ordered, remainder, skip);
  if (milestonePages.length > 0) ordered.push("milestones");
  return ordered;
}

export function writePhaseMetaFiles(phaseDir, orderedPages, milestonePages, writeFile) {
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
}
