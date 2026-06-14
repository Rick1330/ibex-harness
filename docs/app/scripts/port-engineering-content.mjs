#!/usr/bin/env node
/**
 * Draft MDX from engineering markdown sources.
 * Assistant tool — not wholesale copy. Outputs need manual MDX component enrichment.
 *
 * Usage:
 *   node scripts/port-engineering-content.mjs --list
 *   node scripts/port-engineering-content.mjs --map architecture/overview
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { extractSections } from "./lib/port-content-sections.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, "..");
const ENGINEERING_DOCS = path.resolve(APP_ROOT, "../../");
const PUBLIC_DOCS = path.resolve(APP_ROOT, "content/docs");

const PHASE1_CALLOUT = `<Callout type="warning" title="Phase 1 scope">
Content adapted for integrators. Features marked Phase 2+ are not live yet — see [current state](/roadmap/current-state).
</Callout>`;

/** Public slug → { source, sections?, stripPatterns? } */
const CONTENT_MAP = {
  "architecture/overview": {
    source: "ARCHITECTURE.md",
    sections: ["Architecture Overview", "Design Philosophy"],
  },
  "architecture/services": {
    source: "ARCHITECTURE.md",
    sections: ["Core Services"],
  },
  "architecture/data-model": {
    source: "DATABASE_SCHEMA.md",
    sections: ["Core Domain"],
  },
  "architecture/request-lifecycle": {
    source: "ARCHITECTURE.md",
    sections: ["Critical Path Optimization"],
  },
  "security/overview": { source: "SECURITY.md", sections: ["Security Objectives", "Threat Model"] },
  "security/tenant-isolation": { source: "SECURITY.md", sections: ["Multi-Tenancy Isolation"] },
  "security/secrets-and-keys": {
    source: "ENVIRONMENT_VARIABLES.md",
    sections: ["Conventions", "Global Variables"],
  },
  "operations/observability": { source: "OPS_GUIDE.md", sections: [] },
  "operations/troubleshooting": { source: "TROUBLESHOOTING.md", sections: [] },
  "operations/health-checks": { source: "MONITORING.md", sections: [] },
  "operations/incident-response": { source: "runbooks/RUNBOOKS.md", sections: [] },
  "glossary/index": { source: "GLOSSARY.md", sections: [] },
  "deployment/docker-compose": { source: "DEVELOPMENT_GUIDE.md", sections: ["Local Development"] },
  "deployment/environment-variables": { source: "ENVIRONMENT_VARIABLES.md", sections: [] },
};

const STRIP_PATTERNS = [
  /ibex-harness-workspace\/[^\s)`]*/gi,
  /docs\/roadmap\/CURRENT_STATE\.md/gi,
  /docs\/adr\//gi,
];

function stripInternalPaths(text) {
  let out = text;
  for (const re of STRIP_PATTERNS) {
    out = out.replace(re, (m) => {
      if (m.includes("adr")) return "/docs/adr/";
      if (m.includes("CURRENT_STATE")) return "/roadmap/current-state";
      return "contributor workspace";
    });
  }
  return out;
}

function toFrontmatterTitle(slug) {
  const leaf = slug.split("/").pop() ?? slug;
  return leaf
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function draftMdx(slug, body) {
  const title = toFrontmatterTitle(slug);
  const cleaned = stripInternalPaths(body);
  return `---
title: ${title}
description: Draft ported from engineering docs — enrich with MDX components before publishing.
---

${PHASE1_CALLOUT}

${cleaned}
`;
}

function portOne(slug) {
  const entry = CONTENT_MAP[slug];
  if (!entry) {
    console.error(`Unknown map key: ${slug}`);
    console.error("Known:", Object.keys(CONTENT_MAP).join(", "));
    process.exit(1);
  }

  const srcPath = path.join(ENGINEERING_DOCS, entry.source);
  if (!fs.existsSync(srcPath)) {
    console.error(`Source not found: ${srcPath}`);
    process.exit(1);
  }

  const raw = fs.readFileSync(srcPath, "utf8");
  const extracted = extractSections(raw, entry.sections);
  const mdx = draftMdx(slug, extracted);
  const outPath = path.join(PUBLIC_DOCS, `${slug}.mdx`);

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, mdx, "utf8");
  console.log(`Wrote draft: ${outPath}`);
}

const args = process.argv.slice(2);
if (args.includes("--list")) {
  console.log("Content map:");
  for (const [slug, cfg] of Object.entries(CONTENT_MAP)) {
    console.log(`  ${slug} ← ${cfg.source}`);
  }
  process.exit(0);
}

const mapIdx = args.indexOf("--map");
if (mapIdx !== -1 && args[mapIdx + 1]) {
  portOne(args[mapIdx + 1]);
  process.exit(0);
}

console.log("Usage: node scripts/port-engineering-content.mjs --list | --map <slug>");
process.exit(1);
