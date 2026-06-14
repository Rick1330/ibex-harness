import fs from "node:fs";
import path from "node:path";

import { parseFrontmatterFields } from "./roadmap-parse-fields.mjs";

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

export function trackMigratedPage(destName, phaseDir, rel, pages, milestonePages) {
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

export function processMarkdownEntry(ctx, entry, abs, rel, relPath, phaseStub) {
  let content = fs.readFileSync(abs, "utf8");
  const fields = parseFrontmatterFields(content, abs);
  const destName = resolveDestName(ctx.phaseDir, entry, rel, relPath);

  if (entry.name === "README.md" && shouldAppendPhaseStub(ctx.phaseDir, rel)) {
    content = `${content.trim()}${phaseStub}`;
  }

  ctx.writeFile(destName, ctx.toMdx(content, fields));
  trackMigratedPage(destName, ctx.phaseDir, rel, ctx.pages, ctx.milestonePages);
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
    processMarkdownEntry(ctx, entry, abs, rel, relPath, ctx.phaseStub);
  }
}

export function buildOrderedPages(pages, milestonePages) {
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
  return orderedPages;
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
