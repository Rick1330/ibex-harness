import { extractMarkdownField } from "./yaml-frontmatter.mjs";
import { stripMarkdownLinks, stripAfterDelimiter } from "./text-utils.mjs";

export function parseDescriptionMeta(text) {
  return {
    status: extractMarkdownField(text, "Status"),
    completed: extractMarkdownField(text, "Completed"),
    duration: extractMarkdownField(text, "Estimated duration"),
    depends: extractMarkdownField(text, "Depends on"),
    milestone: extractMarkdownField(text, "Current milestone"),
  };
}

function normalizeDescriptionText(raw) {
  return raw.replaceAll("\\n", "\n").replaceAll("**", "");
}

function collapseWhitespace(text) {
  return text.split(" ").filter(Boolean).join(" ");
}

function describeComplete(title, completed) {
  if (!completed) return `${title} — complete.`;
  const trimmed = completed.endsWith(".") ? completed.slice(0, -1) : completed;
  return `${title} — complete as of ${trimmed}.`;
}

function describeInProgress(title, milestone) {
  const current = milestone ? stripMarkdownLinks(milestone) : undefined;
  if (!current) return `${title} — in progress.`;
  return `${title} — in progress. Current: ${current}.`;
}

function describePlanned(title, duration, depends) {
  const parts = [`${title} — planned.`];
  if (duration) parts.push(`Estimated ${duration.toLowerCase()}.`);
  if (depends) parts.push(`Depends on ${depends.toLowerCase()}.`);
  return parts.join(" ");
}

function describeFromStatus(title, status, meta) {
  const lower = status?.toLowerCase() ?? "";
  if (lower.includes("complete")) return describeComplete(title, meta.completed);
  if (lower.includes("progress")) return describeInProgress(title, meta.milestone);
  if (lower.includes("planned")) return describePlanned(title, meta.duration, meta.depends);
  return undefined;
}

export function cleanDescription(raw, title) {
  const text = normalizeDescriptionText(raw);
  if (!text.includes("Status:")) {
    return collapseWhitespace(text);
  }

  const meta = parseDescriptionMeta(text);
  return describeFromStatus(title, meta.status, meta) ?? collapseWhitespace(text);
}
