#!/usr/bin/env node
/**
 * Migrate Phase 3 roadmap from PHASE3_PART1/PART2 source docs
 * into content/roadmap/phase-3-memory-engine/
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { MILESTONE_ORDER } from "./lib/phase3-data.mjs";
import {
  relPathFromSource,
  splitSources,
  writeMdx,
  writePhaseMeta,
  writeStub,
} from "./lib/phase3-migrate.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(__dirname, "..");
const IBEX_R_ROOT = path.resolve(APP_ROOT, "../../..");
const OUTPUT = path.resolve(APP_ROOT, "content/roadmap/phase-3-memory-engine");

const SOURCES = [
  path.join(IBEX_R_ROOT, "PHASE3_PART1_FOUNDATION_AND_SERVICES.md"),
  path.join(IBEX_R_ROOT, "PHASE3_PART2_CONTEXT_API_DASHBOARD_GATE.md"),
];

function migrateSourceSections(sections) {
  const migrated = new Set();

  for (const [filePath, content] of sections) {
    const rel = relPathFromSource(filePath);
    if (!rel) continue;

    writeMdx(OUTPUT, rel, content);
    if (rel.startsWith("milestones/")) {
      migrated.add(rel.replace(/^milestones\//, "").replace(/\.mdx$/, ""));
    }
    console.log(`Wrote ${rel}`);
  }

  return migrated;
}

function writeMissingStubs(migrated) {
  for (const slug of MILESTONE_ORDER) {
    if (migrated.has(slug)) continue;
    writeStub(OUTPUT, slug);
    console.log(`Wrote stub milestones/${slug}.mdx`);
  }
}

function main() {
  fs.mkdirSync(OUTPUT, { recursive: true });
  fs.mkdirSync(path.join(OUTPUT, "milestones"), { recursive: true });

  const sections = splitSources(SOURCES);
  const migrated = migrateSourceSections(sections);
  writeMissingStubs(migrated);
  writePhaseMeta(OUTPUT, MILESTONE_ORDER);

  console.log(`\nMigrated Phase 3 to ${OUTPUT}`);
  console.log(`Sections from source: ${sections.size}, milestones: ${MILESTONE_ORDER.length}`);
}

main();
