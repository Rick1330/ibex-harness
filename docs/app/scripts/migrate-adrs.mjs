#!/usr/bin/env node
/** Migrate docs/adr/*.md → content/docs/adr/*.mdx for the public docs site. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parseAdrIdentity } from "./lib/adr-identity.mjs";
import { extractBoldField } from "./lib/text-utils.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(__dirname, "..");
const LEGACY_ROOT = path.resolve(APP_ROOT, "../adr");
const OUTPUT_ROOT = path.resolve(APP_ROOT, "content/docs/adr");

const ADR_SLUGS = [];

function slugify(filename) {
  const match = filename.match(/^ADR-(\d{4})-(.+)\.md$/i);
  if (!match) return null;
  return `${match[1]}-${match[2].toLowerCase()}`;
}

function parseAdrMetadata(content) {
  return {
    status: extractBoldField(content, "Status"),
    date: extractBoldField(content, "Date"),
    authors: extractBoldField(content, "Authors"),
  };
}

function parseAdr(content, filename) {
  return {
    ...parseAdrIdentity(content, filename),
    ...parseAdrMetadata(content),
  };
}

function rewriteBody(content) {
  let body = content.trim();

  body = body.replace(
    /\]\(ADR-(\d{4})-([^)]+\.md)\)/gi,
    (_, id, rest) => `](/docs/adr/${id}-${rest.replace(/\.md$/i, "").toLowerCase()})`,
  );

  body = body.replace(
    /\]\(\.\.\/roadmap\/([^)]+\.md)\)/gi,
    (_, p) => {
      const slug = p.replace(/\.md$/i, "").replace(/README$/i, "index").toLowerCase();
      return `](/roadmap/${slug})`;
    },
  );

  body = body.replace(
    /\]\(\.\.\/([^)]+\.md)\)/g,
    (_, p) => `](/docs/${p.replace(/\.md$/i, "").toLowerCase()})`,
  );

  body = body.replace(/<(\d)/g, "&lt;$1");
  body = body.replace(/<!--[\s\S]*?-->/g, "");

  return body;
}

function toMdx(content, meta) {
  const fm = ["---"];
  fm.push(`title: ${JSON.stringify(meta.title)}`);
  fm.push(`description: ${JSON.stringify(`Architecture decision record ${meta.adrId}.`)}`);
  fm.push(`adrId: ${JSON.stringify(meta.adrId)}`);
  if (meta.status) fm.push(`status: ${JSON.stringify(meta.status)}`);
  if (meta.date) fm.push(`date: ${JSON.stringify(meta.date)}`);
  if (meta.authors) fm.push(`authors: ${JSON.stringify(meta.authors)}`);
  fm.push("---", "", rewriteBody(content));
  return fm.join("\n");
}

function main() {
  if (!fs.existsSync(LEGACY_ROOT)) {
    console.error(`ADR source not found: ${LEGACY_ROOT}`);
    process.exit(1);
  }

  fs.rmSync(OUTPUT_ROOT, { recursive: true, force: true });
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });

  const files = fs
    .readdirSync(LEGACY_ROOT)
    .filter((f) => /^ADR-\d{4}-/.test(f) && !f.includes("template"))
    .sort();

  for (const file of files) {
    const slug = slugify(file);
    if (!slug) continue;
    const content = fs.readFileSync(path.join(LEGACY_ROOT, file), "utf8");
    const meta = parseAdr(content, file);
    fs.writeFileSync(path.join(OUTPUT_ROOT, `${slug}.mdx`), toMdx(content, meta), "utf8");
    ADR_SLUGS.push(slug);
  }

  fs.writeFileSync(
    path.join(OUTPUT_ROOT, "index.mdx"),
    `---
title: Architecture Decision Records
description: Accepted architecture decisions for IBEX Harness — auth, proxy, migrations, observability, and docs site.
---

# Architecture Decision Records

Durable technical decisions for IBEX Harness. Each ADR captures context, the decision, and consequences.

Browse the sidebar for individual records (ADR-0002 through ADR-${ADR_SLUGS.at(-1)?.slice(0, 4) ?? "0023"}).

For contributors: edit \`docs/app/content/docs/adr/\` and run \`pnpm exec fumadocs-mdx\` in \`docs/app/\`.
`,
    "utf8",
  );

  fs.writeFileSync(
    path.join(OUTPUT_ROOT, "meta.json"),
    JSON.stringify({ title: "ADRs", pages: ["index", ...ADR_SLUGS] }, null, 2) + "\n",
  );

  console.log(`Migrated ${ADR_SLUGS.length} ADRs to ${OUTPUT_ROOT}`);
}

main();
