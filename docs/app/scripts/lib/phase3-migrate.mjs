import fs from "node:fs";
import path from "node:path";

import { PHASE, PHASE_FULL, STUBS } from "./phase3-data.mjs";

function parseStatus(raw) {
  const value = raw.trim().toLowerCase();
  if (value.includes("complete")) return "completed";
  if (value.includes("progress")) return "in-progress";
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

export function rewriteBody(body) {
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

  return out.replace(/^# Phase 3 — Goals\s*$/m, "# Phase 3 — Goals");
}

function rewriteGoalLinks(goal) {
  if (!goal) return goal;
  return goal
    .replace(/\]\(\.\.\/goals\.md#([^)]+)\)/, `](/roadmap/${PHASE}/goals#$1)`)
    .replace(/\(goals\.md#([^)]+)\)/, `(/roadmap/${PHASE}/goals#$1)`);
}

function summaryFromWhySection(content) {
  const why = content.match(
    /## Why This Milestone Exists\s*\n+([\s\S]*?)(?=\n## |\n---|\n$)/i,
  );
  if (!why) return undefined;

  return why[1]
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(" ")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1")
    .slice(0, 320);
}

function summaryFromFirstParagraph(content) {
  const para = content
    .replace(/^#.+$/m, "")
    .split("\n\n")
    .map((part) => part.trim())
    .find((part) => part && !part.startsWith("#") && !part.startsWith("|") && !part.startsWith("```"));

  return para?.replace(/\[(.+?)\]\(.+?\)/g, "$1").slice(0, 320) ?? "";
}

export function parseFields(content, relPath) {
  const h1 = content.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? "Untitled";
  const status = parseStatus(content.match(/\*\*Status:\*\*\s*(.+)/i)?.[1] ?? "Planned");
  const effort = content.match(/\*\*Estimated effort:\*\*\s*(.+)/i)?.[1]?.trim();
  const goal = rewriteGoalLinks(content.match(/\*\*Goal:\*\*\s*(.+)/i)?.[1]?.trim());
  const milestoneId =
    relPath.match(/milestones\/(\d+\.\d+\.\d+)/)?.[1] ??
    h1.match(/^Milestone\s+(\d+\.\d+\.\d+)/i)?.[1];

  const summary = summaryFromWhySection(content) ?? summaryFromFirstParagraph(content);
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

export function buildFrontmatter(fields) {
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

export function writeMdx(outputRoot, relPath, body, extraFields = {}) {
  const fields = { ...parseFields(body, relPath), ...extraFields };
  const transformed = rewriteBody(body.trim());
  const out = `${buildFrontmatter(fields)}\n\n${transformed}\n`;
  const full = path.join(outputRoot, relPath);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, out, "utf8");
  return relPath;
}

export function splitSources(sources) {
  const sections = new Map();

  for (const src of sources) {
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

export function relPathFromSource(filePath) {
  if (filePath === "README.md") return "index.mdx";
  if (filePath === "goals.md") return "goals.mdx";
  if (filePath.startsWith("milestones/")) return filePath.replace(/\.md$/, ".mdx");
  return undefined;
}

export function writeStub(outputRoot, slug) {
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

  writeMdx(outputRoot, `milestones/${slug}.mdx`, body, {
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

export function writePhaseMeta(outputRoot, milestoneOrder) {
  fs.writeFileSync(
    path.join(outputRoot, "meta.json"),
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
    path.join(outputRoot, "milestones", "meta.json"),
    `${JSON.stringify(
      {
        title: "Milestones",
        icon: "Flag",
        pages: milestoneOrder,
      },
      null,
      2,
    )}\n`,
  );
}
