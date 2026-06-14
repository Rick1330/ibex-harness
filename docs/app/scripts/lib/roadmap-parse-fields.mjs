import path from "node:path";

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
  if (value.includes("planned")) return "planned";
  return undefined;
}

function parseTitle(content, filePath) {
  return extractH1Title(content) ?? path.basename(filePath, ".md");
}

function parseMarkdownMeta(content) {
  return {
    status: parseStatus(extractBoldField(content, "Status") ?? ""),
    estimatedEffort: extractBoldField(content, "Estimated effort"),
    goal: extractBoldField(content, "Goal"),
  };
}

function isNumericPart(part) {
  return part.length > 0 && Number.isInteger(Number(part));
}

function parseNumericMilestoneId(base) {
  const parts = base.split(".");
  if (parts.length !== 3 || !parts.every(isNumericPart)) return undefined;
  return base.toLowerCase();
}

function parseDecoMilestoneId(base) {
  const lower = base.toLowerCase();
  if (!lower.startsWith("d")) return undefined;
  const parts = lower.slice(1).split(".");
  if (parts.length !== 2 || !parts.every(isNumericPart)) return undefined;
  return lower;
}

function parseMilestoneId(filePath) {
  const base = path.basename(filePath, ".md");
  return parseNumericMilestoneId(base) ?? parseDecoMilestoneId(base);
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

function stripFrontmatter(content) {
  if (!content.startsWith("---\n")) return content;
  const end = content.indexOf("\n---\n", 4);
  if (end === -1) return content;
  return content.slice(end + 5);
}

function summaryFromFirstParagraph(content) {
  const withoutFrontmatter = stripFrontmatter(content);
  const withoutH1 = withoutFrontmatter
    .split("\n")
    .filter((line) => !line.startsWith("# "))
    .join("\n");

  const firstPara = withoutH1
    .split("\n\n")
    .map((part) => part.trim())
    .find((part) => part && !part.startsWith("#") && !part.startsWith("|") && !part.startsWith("```"));

  return firstPara ? stripMarkdownLinks(firstPara).slice(0, 320) : undefined;
}

function parseSummary(content) {
  return summaryFromWhySection(content) ?? summaryFromFirstParagraph(content);
}

function parsePhase(filePath) {
  const normalized = filePath.replaceAll("\\", "/");
  const marker = "phase-";
  const index = normalized.indexOf(marker);
  if (index === -1) return undefined;
  const rest = normalized.slice(index);
  const slash = rest.indexOf("/");
  return slash === -1 ? rest : rest.slice(0, slash);
}

export function parseFrontmatterFields(content, filePath) {
  const meta = parseMarkdownMeta(content);
  return {
    title: parseTitle(content, filePath),
    ...meta,
    milestoneId: parseMilestoneId(filePath),
    summary: parseSummary(content),
    phase: parsePhase(filePath),
  };
}
