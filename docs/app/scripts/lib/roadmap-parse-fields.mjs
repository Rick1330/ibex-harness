import path from "node:path";

function parseStatus(raw) {
  const value = raw.trim().toLowerCase();
  if (value.includes("complete")) return "completed";
  if (value.includes("progress")) return "in-progress";
  if (value.includes("planned")) return "planned";
  return undefined;
}

function parseTitle(content, filePath) {
  const titleMatch = content.match(/^#\s+(.+)$/m);
  return titleMatch?.[1]?.trim() ?? path.basename(filePath, ".md");
}

function parseMarkdownMeta(content) {
  const statusMatch = content.match(/\*\*Status:\*\*\s*(.+)/i);
  const effortMatch = content.match(/\*\*Estimated effort:\*\*\s*(.+)/i);
  const goalMatch = content.match(/\*\*Goal:\*\*\s*(.+)/i);

  return {
    status: statusMatch ? parseStatus(statusMatch[1]) : undefined,
    estimatedEffort: effortMatch?.[1]?.trim(),
    goal: goalMatch?.[1]?.trim(),
  };
}

function parseMilestoneId(filePath) {
  const base = path.basename(filePath, ".md");
  const idMatch = base.match(/^(\d+\.\d+\.\d+|d\d+\.\d+)/i);
  return idMatch?.[1]?.toLowerCase();
}

function summaryFromWhySection(content) {
  const whySection = content.match(
    /## Why This Milestone Exists\s*\n+([\s\S]*?)(?=\n## |\n---|\n$)/i,
  );
  if (!whySection) return undefined;

  return whySection[1]
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(" ")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1")
    .slice(0, 320);
}

function summaryFromFirstParagraph(content) {
  const firstPara = content
    .replace(/^---[\s\S]*?---\n/m, "")
    .replace(/^#.+$/m, "")
    .split("\n\n")
    .map((p) => p.trim())
    .find((p) => p && !p.startsWith("#") && !p.startsWith("|") && !p.startsWith("```"));

  return firstPara?.replace(/\[(.+?)\]\(.+?\)/g, "$1").slice(0, 320);
}

function parseSummary(content) {
  return summaryFromWhySection(content) ?? summaryFromFirstParagraph(content);
}

function parsePhase(filePath) {
  return filePath.match(/phase-[^/\\]+/)?.[0];
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
