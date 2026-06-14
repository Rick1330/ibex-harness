import fs from "node:fs";
import path from "node:path";

import { PHASE, PHASE_FULL, STUBS } from "./phase3-data.mjs";
import { simplifyAdrBackticks } from "./adr-backtick-rewrite.mjs";
import { rewriteAllMarkdownLinks } from "./markdown-link-rewrite.mjs";
import {
  extractBoldField,
  extractH1Title,
  extractSectionAfterHeading,
  stripMarkdownLinks,
} from "./text-utils.mjs";

function parseStatus(raw) {
  const value = raw.trim().toLowerCase();
  if (value.includes("complete")) return "completed";
  if (value.includes("progress")) return "in-progress";
  return "planned";
}

function trimEdgeDashes(value) {
  let start = 0;
  let end = value.length;
  while (start < end && value[start] === "-") start += 1;
  while (end > start && value[end - 1] === "-") end -= 1;
  return value.slice(start, end);
}

function slugifyTitle(title) {
  let slug = "";
  let lastWasDash = true;

  for (const char of title.toLowerCase()) {
    const isAlphaNum = (char >= "a" && char <= "z") || (char >= "0" && char <= "9");
    if (isAlphaNum) {
      slug += char;
      lastWasDash = false;
      continue;
    }
    if (!lastWasDash) {
      slug += "-";
      lastWasDash = true;
    }
  }

  return trimEdgeDashes(slug);
}

function stripMarkdownExtension(pathPart) {
  let cleaned = pathPart;
  if (cleaned.endsWith(".mdx")) cleaned = cleaned.slice(0, -4);
  else if (cleaned.endsWith(".md")) cleaned = cleaned.slice(0, -3);
  if (cleaned.endsWith("/README") || cleaned === "README") cleaned = "index";
  return cleaned;
}

function rewriteDocRoadmapLink(matchText, pathPart) {
  return `[${matchText}](/roadmap/${stripMarkdownExtension(pathPart)})`;
}

function isGoalNumber(value) {
  const parts = value.split(".");
  return parts.length === 2 && parts.every((part) => part.length > 0 && Number.isInteger(Number(part)));
}

function goalAnchorId(num, title) {
  const n = num.replaceAll(".", "");
  return `goal-${n}-${slugifyTitle(title)}`;
}

function rewriteExternalRoadmapLinks(out) {
  const marker = "docs/roadmap/phase-3-memory-engine/";
  return rewriteAllMarkdownLinks(out, (link) => {
    if (!link.pathPart.startsWith(marker)) {
      const suffix = link.hash ? `#${link.hash}` : "";
      return `[${link.text}](${link.pathPart}${suffix})`;
    }
    return rewriteDocRoadmapLink(link.text, link.pathPart.slice(marker.length));
  });
}

export function rewriteBody(body) {
  let out = body;

  out = out.replaceAll("](../goals.md#", `](/roadmap/${PHASE}/goals#`);
  out = out.replaceAll("(goals.md#", `(/roadmap/${PHASE}/goals#`);
  out = out.replaceAll("docs/roadmap/phase-3-memory-engine/", `/roadmap/${PHASE}/`);
  out = rewriteExternalRoadmapLinks(out);
  out = simplifyAdrBackticks(out);

  out = out
    .split("\n")
    .map((line) => {
      if (line.trimEnd() === "# Phase 3 — Goals") return "# Phase 3 — Goals";

      const prefix = "## Goal ";
      if (!line.startsWith(prefix)) return line;
      const colonIndex = line.indexOf(": ", prefix.length);
      if (colonIndex === -1) return line;
      const num = line.slice(prefix.length, colonIndex).trim();
      const title = line.slice(colonIndex + 2).trim();
      if (!isGoalNumber(num)) return line;
      const id = goalAnchorId(num, title);
      return `<h2 id="${id}">Goal ${num}: ${title}</h2>`;
    })
    .join("\n");

  return out;
}

function rewriteGoalLinks(goal) {
  if (!goal) return goal;
  return goal
    .replaceAll("](../goals.md#", `](/roadmap/${PHASE}/goals#`)
    .replaceAll("(goals.md#", `(/roadmap/${PHASE}/goals#`);
}

function summaryFromWhySection(content) {
  const section = extractSectionAfterHeading(content, "Why This Milestone Exists");
  if (!section) return undefined;

  return stripMarkdownLinks(
    section
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 2)
      .join(" "),
  ).slice(0, 320);
}

function summaryFromFirstParagraph(content) {
  const withoutH1 = content
    .split("\n")
    .filter((line) => !line.startsWith("# "))
    .join("\n");

  const para = withoutH1
    .split("\n\n")
    .map((part) => part.trim())
    .find((part) => part && !part.startsWith("#") && !part.startsWith("|") && !part.startsWith("```"));

  return para ? stripMarkdownLinks(para).slice(0, 320) : "";
}

function parseMilestoneIdFromPath(relPath) {
  const marker = "milestones/";
  const index = relPath.indexOf(marker);
  if (index === -1) return undefined;

  const rest = relPath.slice(index + marker.length);
  const slash = rest.indexOf("/");
  const raw = slash === -1 ? rest : rest.slice(0, slash);
  const candidate = raw.endsWith(".mdx") ? raw.slice(0, -4) : raw;
  const parts = candidate.split(".");
  if (parts.length !== 3) return undefined;
  if (!parts.every((part) => part.length > 0 && Number.isInteger(Number(part)))) {
    return undefined;
  }
  return candidate;
}

function parseMilestoneIdFromTitle(h1) {
  if (!h1.toLowerCase().startsWith("milestone ")) return undefined;
  const rest = h1.slice("Milestone ".length).trim();
  const space = rest.indexOf(" ");
  const candidate = space === -1 ? rest : rest.slice(0, space);
  const parts = candidate.split(".");
  if (parts.length !== 3) return undefined;
  if (!parts.every((part) => part.length > 0 && Number.isInteger(Number(part)))) {
    return undefined;
  }
  return candidate;
}

function parsePhase3Identity(content, relPath) {
  const h1 = extractH1Title(content) ?? "Untitled";
  const isIndex = relPath.endsWith("index.mdx") || relPath.includes("README");
  const isGoals = relPath.includes("goals.mdx");
  const milestoneId =
    parseMilestoneIdFromPath(relPath) ?? parseMilestoneIdFromTitle(h1);

  return {
    title: h1,
    fullTitle: isIndex ? PHASE_FULL : h1,
    milestoneId,
    isIndex,
    isGoals,
  };
}

function parsePhase3Goal(content) {
  const effort = extractBoldField(content, "Estimated effort");
  const goal = rewriteGoalLinks(extractBoldField(content, "Goal"));
  const status = parseStatus(extractBoldField(content, "Status") ?? "Planned");

  return { effort, goal, status };
}

function parsePhase3Summary(content) {
  return summaryFromWhySection(content) ?? summaryFromFirstParagraph(content);
}

export function parseFields(content, relPath) {
  const identity = parsePhase3Identity(content, relPath);
  const goalFields = parsePhase3Goal(content);
  const summary = parsePhase3Summary(content);

  return {
    title: identity.title,
    fullTitle: identity.fullTitle,
    description: summary,
    summary,
    status: identity.isIndex || identity.isGoals ? "planned" : goalFields.status,
    milestoneId: identity.milestoneId,
    goal: goalFields.goal,
    estimatedEffort: goalFields.effort,
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
