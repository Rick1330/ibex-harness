#!/usr/bin/env node
/**
 * Migrate Phase 3 roadmap from PHASE3_PART1/PART2 source docs
 * into content/roadmap/phase-3-memory-engine/
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(__dirname, "..");
const IBEX_R_ROOT = path.resolve(APP_ROOT, "../../..");
const OUTPUT = path.resolve(APP_ROOT, "content/roadmap/phase-3-memory-engine");
const PHASE = "phase-3-memory-engine";
const PHASE_FULL = "Phase 3 — Memory Engine and Operator Platform";

const SOURCES = [
  path.join(IBEX_R_ROOT, "PHASE3_PART1_FOUNDATION_AND_SERVICES.md"),
  path.join(IBEX_R_ROOT, "PHASE3_PART2_CONTEXT_API_DASHBOARD_GATE.md"),
];

const MILESTONE_ORDER = [
  "3.1.1-memory-schema-migrations",
  "3.1.2-python-database-models",
  "3.2.1-embedding-service-skeleton",
  "3.2.2-embedding-batch-endpoint",
  "3.2.3-embedding-cache",
  "3.2.4-embedding-service-production-readiness",
  "3.3.1-memory-service-skeleton",
  "3.3.2-memory-write-pipeline",
  "3.3.3-memory-deduplication",
  "3.3.4-pgvector-semantic-search",
  "3.3.5-hot-memory-cache",
  "3.3.6-memory-ranking-composite-score",
  "3.4.1-worker-service-skeleton",
  "3.4.2-session-incremental-read",
  "3.4.3-memory-extraction-task",
  "3.4.4-memory-embedding-task",
  "3.4.5-conflict-detection",
  "3.4.6-worker-reliability-and-dlq",
  "3.5.1-context-assembly-skeleton",
  "3.5.2-token-budget-calculator",
  "3.5.3-memory-retrieval-pipeline",
  "3.5.4-memory-scorer",
  "3.5.5-greedy-knapsack-packer",
  "3.5.6-context-formatter",
  "3.5.7-proxy-context-assembly-integration",
  "3.6.1-api-server-skeleton",
  "3.6.2-org-user-management-api",
  "3.6.3-agent-management-api",
  "3.6.4-token-management-api",
  "3.6.5-directive-management-api",
  "3.6.6-memory-management-api",
  "3.6.7-analytics-api",
  "3.6.8-api-openapi-pagination-gate",
  "3.7.1-minio-session-archives",
  "3.7.2-session-archive-read-presigned",
  "3.7.3-session-archive-gdpr-deletion",
  "3.8.1-dashboard-skeleton",
  "3.8.2-agent-management-ui",
  "3.8.3-directive-management-ui",
  "3.8.4-memory-browser",
  "3.8.5-analytics-dashboard",
  "3.8.6-session-replay-viewer",
  "3.9.1-e2e-memory-integration-test",
  "3.9.2-context-assembly-load-test",
  "3.9.3-phase3-exit-gate",
];

const STUBS = {
  "3.2.2-embedding-batch-endpoint": {
    id: "3.2.2",
    title: "Embedding Batch Endpoint",
    goal: "3.2",
    goalLabel: "Embedding service",
    anchor: "goal-32-embedding-service",
    effort: "2 days",
  },
  "3.2.4-embedding-service-production-readiness": {
    id: "3.2.4",
    title: "Embedding Service Production Readiness",
    goal: "3.2",
    goalLabel: "Embedding service",
    anchor: "goal-32-embedding-service",
    effort: "2 days",
  },
  "3.3.3-memory-deduplication": {
    id: "3.3.3",
    title: "Memory Deduplication",
    goal: "3.3",
    goalLabel: "Memory service",
    anchor: "goal-33-memory-service",
    effort: "3 days",
  },
  "3.3.5-hot-memory-cache": {
    id: "3.3.5",
    title: "Hot Memory Cache (Redis Sorted Set)",
    goal: "3.3",
    goalLabel: "Memory service",
    anchor: "goal-33-memory-service",
    effort: "2 days",
  },
  "3.3.6-memory-ranking-composite-score": {
    id: "3.3.6",
    title: "Memory Ranking Composite Score",
    goal: "3.3",
    goalLabel: "Memory service",
    anchor: "goal-33-memory-service",
    effort: "3 days",
  },
  "3.4.2-session-incremental-read": {
    id: "3.4.2",
    title: "Session Incremental Read Pointer",
    goal: "3.4",
    goalLabel: "Memory extraction worker",
    anchor: "goal-34-memory-extraction-worker",
    effort: "2 days",
  },
  "3.4.4-memory-embedding-task": {
    id: "3.4.4",
    title: "Memory Embedding Task",
    goal: "3.4",
    goalLabel: "Memory extraction worker",
    anchor: "goal-34-memory-extraction-worker",
    effort: "2 days",
  },
  "3.4.6-worker-reliability-and-dlq": {
    id: "3.4.6",
    title: "Worker Reliability and DLQ",
    goal: "3.4",
    goalLabel: "Memory extraction worker",
    anchor: "goal-34-memory-extraction-worker",
    effort: "2 days",
  },
  "3.6.2-org-user-management-api": {
    id: "3.6.2",
    title: "Organization and User Management API",
    goal: "3.6",
    goalLabel: "Management API server",
    anchor: "goal-36-management-api-server",
    effort: "3 days",
  },
  "3.6.4-token-management-api": {
    id: "3.6.4",
    title: "Token Management API",
    goal: "3.6",
    goalLabel: "Management API server",
    anchor: "goal-36-management-api-server",
    effort: "2 days",
  },
  "3.6.8-api-openapi-pagination-gate": {
    id: "3.6.8",
    title: "OpenAPI Spec and Pagination Gate",
    goal: "3.6",
    goalLabel: "Management API server",
    anchor: "goal-36-management-api-server",
    effort: "2 days",
  },
  "3.7.2-session-archive-read-presigned": {
    id: "3.7.2",
    title: "Session Archive Read (Pre-signed URLs)",
    goal: "3.7",
    goalLabel: "MinIO session content archives",
    anchor: "goal-37-minio-session-content-archives",
    effort: "2 days",
  },
  "3.7.3-session-archive-gdpr-deletion": {
    id: "3.7.3",
    title: "Session Archive GDPR Deletion Cascade",
    goal: "3.7",
    goalLabel: "MinIO session content archives",
    anchor: "goal-37-minio-session-content-archives",
    effort: "2 days",
  },
  "3.8.2-agent-management-ui": {
    id: "3.8.2",
    title: "Agent Management UI",
    goal: "3.8",
    goalLabel: "Operator dashboard",
    anchor: "goal-38-operator-dashboard",
    effort: "3 days",
  },
  "3.8.3-directive-management-ui": {
    id: "3.8.3",
    title: "Directive Management UI",
    goal: "3.8",
    goalLabel: "Operator dashboard",
    anchor: "goal-38-operator-dashboard",
    effort: "3 days",
  },
  "3.8.6-session-replay-viewer": {
    id: "3.8.6",
    title: "Session Replay Viewer",
    goal: "3.8",
    goalLabel: "Operator dashboard",
    anchor: "goal-38-operator-dashboard",
    effort: "4 days",
  },
};

function parseStatus(raw) {
  const value = raw.trim().toLowerCase();
  if (value.includes("complete")) return "completed";
  if (value.includes("progress")) return "in-progress";
  if (value.includes("planned")) return "planned";
  return "planned";
}

function goalAnchorId(num, title) {
  const n = num.replace(".", "");
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `goal-${n}-${slug}`;
}

function rewriteBody(body) {
  let out = body;

  out = out.replace(/\]\(\.\.\/goals\.md#([^)]+)\)/g, `](/roadmap/${PHASE}/goals#$1)`);
  out = out.replace(/\(goals\.md#([^)]+)\)/g, `(/roadmap/${PHASE}/goals#$1)`);
  out = out.replace(/docs\/roadmap\/phase-3-memory-engine\//g, `/roadmap/${PHASE}/`);
  out = out.replace(/\[([^\]]+)\]\(docs\/roadmap\/phase-3-memory-engine\/([^)]+)\)/g, "[$1](/roadmap/$2)");
  out = out.replace(/`docs\/adr\/ADR-(\d{4})-([^`]+)`/g, "`ADR-$1`");
  out = out.replace(
    /Write `docs\/adr\/ADR-(\d{4})-([^`]+)`/g,
    "Write ADR-$1 (engineering `docs/adr/` — promote to `/docs/adr/` when accepted)",
  );

  out = out.replace(/^## Goal (3\.\d+): (.+)$/gm, (_, num, title) => {
    const id = goalAnchorId(num, title);
    return `<h2 id="${id}">Goal ${num}: ${title}</h2>`;
  });

  out = out.replace(/^# Phase 3 — Goals\s*$/m, "# Phase 3 — Goals");

  return out;
}

function parseFields(content, relPath) {
  const h1 = content.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? "Untitled";
  const status = parseStatus(content.match(/\*\*Status:\*\*\s*(.+)/i)?.[1] ?? "Planned");
  const effort = content.match(/\*\*Estimated effort:\*\*\s*(.+)/i)?.[1]?.trim();
  let goal = content.match(/\*\*Goal:\*\*\s*(.+)/i)?.[1]?.trim();
  if (goal) {
    goal = goal.replace(/\]\(\.\.\/goals\.md#([^)]+)\)/, `](/roadmap/${PHASE}/goals#$1)`);
    goal = goal.replace(/\(goals\.md#([^)]+)\)/, `(/roadmap/${PHASE}/goals#$1)`);
  }

  const milestoneId =
    relPath.match(/milestones\/(\d+\.\d+\.\d+)/)?.[1] ??
    h1.match(/^Milestone\s+(\d+\.\d+\.\d+)/i)?.[1];

  let summary;
  const why = content.match(
    /## Why This Milestone Exists\s*\n+([\s\S]*?)(?=\n## |\n---|\n$)/i,
  );
  if (why) {
    summary = why[1]
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(0, 2)
      .join(" ")
      .replace(/\[(.+?)\]\(.+?\)/g, "$1")
      .slice(0, 320);
  } else {
    const para = content
      .replace(/^#.+$/m, "")
      .split("\n\n")
      .map((p) => p.trim())
      .find((p) => p && !p.startsWith("#") && !p.startsWith("|") && !p.startsWith("```"));
    summary = para?.replace(/\[(.+?)\]\(.+?\)/g, "$1").slice(0, 320) ?? "";
  }

  const isIndex = relPath.endsWith("index.mdx") || relPath.includes("README");
  const isGoals = relPath.includes("goals.mdx");
  const fullTitle = isIndex ? PHASE_FULL : h1;

  return {
    title: h1,
    fullTitle,
    description: summary,
    summary,
    status: isIndex || isGoals ? "planned" : status,
    milestoneId,
    goal,
    estimatedEffort: effort,
    phase: PHASE,
  };
}

function buildFrontmatter(fields) {
  const fm = ["---"];
  fm.push(`title: ${JSON.stringify(fields.title)}`);
  if (fields.fullTitle && fields.fullTitle !== fields.title) {
    fm.push(`fullTitle: ${JSON.stringify(fields.fullTitle)}`);
  }
  if (fields.description) fm.push(`description: ${JSON.stringify(fields.description)}`);
  if (fields.summary) fm.push(`summary: ${JSON.stringify(fields.summary)}`);
  if (fields.status) fm.push(`status: ${JSON.stringify(fields.status)}`);
  if (fields.milestoneId) fm.push(`milestoneId: ${JSON.stringify(fields.milestoneId)}`);
  if (fields.goal) fm.push(`goal: ${JSON.stringify(fields.goal)}`);
  if (fields.estimatedEffort) fm.push(`estimatedEffort: ${JSON.stringify(fields.estimatedEffort)}`);
  fm.push(`phase: ${JSON.stringify(fields.phase)}`);
  fm.push("---");
  return fm.join("\n");
}

function writeMdx(relPath, body, extraFields = {}) {
  const fields = { ...parseFields(body, relPath), ...extraFields };
  const transformed = rewriteBody(body.trim());
  const out = `${buildFrontmatter(fields)}\n\n${transformed}\n`;
  const full = path.join(OUTPUT, relPath);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, out, "utf8");
  return relPath;
}

function splitSources() {
  const sections = new Map();

  for (const src of SOURCES) {
    if (!fs.existsSync(src)) {
      console.error(`Missing source: ${src}`);
      process.exit(1);
    }
    const raw = fs.readFileSync(src, "utf8");
    const parts = raw.split(/# FILE: docs\/roadmap\/phase-3-memory-engine\//);

    for (let i = 1; i < parts.length; i++) {
      const nl = parts[i].indexOf("\n");
      const filePath = parts[i].slice(0, nl).trim();
      const content = parts[i].slice(nl + 1).trim();
      sections.set(filePath, content);
    }
  }

  return sections;
}

function writeStub(slug) {
  const stub = STUBS[slug];
  if (!stub) return;

  const fullTitle = `Milestone ${stub.id} — ${stub.title}`;
  const goalLink = `[${stub.goal} — ${stub.goalLabel}](/roadmap/${PHASE}/goals#${stub.anchor})`;
  const body = `# ${fullTitle}

**Status:** Planned  
**Goal:** ${goalLink}  
**Phase:** 3 — Memory Engine and Operator Platform  
**Estimated effort:** ${stub.effort}

---

<Callout type="note" title="Spec pending">
  Detailed milestone specification is not yet published. Scope is defined in [Goal ${stub.goal}](/roadmap/${PHASE}/goals#${stub.anchor}) acceptance criteria and the Phase 3 execution order on the [phase index](/roadmap/${PHASE}).
</Callout>
`;

  writeMdx(`milestones/${slug}.mdx`, body, {
    title: fullTitle,
    fullTitle,
    milestoneId: stub.id,
    goal: goalLink,
    estimatedEffort: stub.effort,
    status: "planned",
    description: `${stub.title} — detailed spec pending.`,
    summary: `${stub.title} — detailed spec pending.`,
  });
}

function main() {
  fs.mkdirSync(OUTPUT, { recursive: true });
  fs.mkdirSync(path.join(OUTPUT, "milestones"), { recursive: true });

  const sections = splitSources();
  const migrated = new Set();

  for (const [filePath, content] of sections) {
    let rel;
    if (filePath === "README.md") rel = "index.mdx";
    else if (filePath === "goals.md") rel = "goals.mdx";
    else if (filePath.startsWith("milestones/")) {
      rel = filePath.replace(/\.md$/, ".mdx");
    } else {
      continue;
    }

    writeMdx(rel, content);
    if (rel.startsWith("milestones/")) {
      migrated.add(rel.replace(/^milestones\//, "").replace(/\.mdx$/, ""));
    }
    console.log(`Wrote ${rel}`);
  }

  for (const slug of MILESTONE_ORDER) {
    if (!migrated.has(slug) && STUBS[slug]) {
      writeStub(slug);
      console.log(`Wrote stub milestones/${slug}.mdx`);
    }
  }

  fs.writeFileSync(
    path.join(OUTPUT, "meta.json"),
    `${JSON.stringify(
      {
        title: "Phase 3 memory engine",
        icon: "Lightbulb",
        pages: ["index", "goals", "decisions", "risks", "milestones"],
      },
      null,
      2,
    )}\n`,
  );

  fs.writeFileSync(
    path.join(OUTPUT, "milestones", "meta.json"),
    `${JSON.stringify(
      {
        title: "Milestones",
        icon: "Flag",
        pages: MILESTONE_ORDER,
      },
      null,
      2,
    )}\n`,
  );

  console.log(`\nMigrated Phase 3 to ${OUTPUT}`);
  console.log(`Sections from source: ${sections.size}, milestones: ${MILESTONE_ORDER.length}`);
}

main();
