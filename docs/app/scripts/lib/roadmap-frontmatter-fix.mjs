import { cleanDescription } from "./roadmap-description.mjs";
import {
  extractMarkdownField,
  matchYamlField,
  readYamlValue,
  setYamlField,
} from "./yaml-frontmatter.mjs";
import { findYamlLine, readYamlLineValue } from "./text-utils.mjs";

function needsDescriptionCleanup(val) {
  return (
    val.includes("**") ||
    val.includes("\\n") ||
    val.toLowerCase().includes("status:") ||
    val.includes("Exit audit:")
  );
}

function fixYamlDescriptions(fm, title) {
  let out = fm;
  for (const key of ["description", "summary"]) {
    const match = matchYamlField(out, key);
    if (!match) continue;
    const val = readYamlValue(match[1]);
    if (needsDescriptionCleanup(val)) {
      out = setYamlField(out, key, cleanDescription(val, title));
    }
  }
  return out;
}

function normalizeCompletedDateLine(fm) {
  const line = findYamlLine(fm, "completedDate");
  if (!line) return fm;

  const raw = readYamlLineValue(line, "completedDate");
  if (!raw) return fm;

  const val = readYamlValue(raw);
  const newlineIndex = val.indexOf("\\n");
  const trimmed = newlineIndex === -1 ? val : val.slice(0, newlineIndex);
  return setYamlField(fm, "completedDate", trimmed.trim());
}

function statusFromText(raw) {
  if (!raw) return undefined;
  const lower = raw.toLowerCase();
  if (lower.includes("complete")) return "completed";
  if (lower.includes("progress")) return "in-progress";
  if (lower.includes("planned")) return "planned";
  return undefined;
}

function syncStatusField(fm, body) {
  const statusRaw =
    extractMarkdownField(body.slice(0, 800), "Status") ??
    extractMarkdownField(fm, "Status");
  const status = statusFromText(statusRaw);
  if (!status || findYamlLine(fm, "status")) return fm;
  return setYamlField(fm, "status", status);
}

function syncCompletedDateField(fm, body) {
  const completed =
    extractMarkdownField(fm, "Completed") ??
    extractMarkdownField(body.slice(0, 500), "Completed");
  if (!completed || findYamlLine(fm, "completedDate")) return fm;
  return setYamlField(fm, "completedDate", completed);
}

export function fixFrontmatter(fm, body) {
  const titleLine = findYamlLine(fm, "title");
  const title = readYamlValue(readYamlLineValue(titleLine ?? "", "title") ?? "Untitled");

  let out = fixYamlDescriptions(fm, title);
  out = normalizeCompletedDateLine(out);
  out = syncStatusField(out, body);
  out = syncCompletedDateField(out, body);
  return out;
}
