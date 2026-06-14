import { cleanDescription } from "./roadmap-description.mjs";
import {
  extractMarkdownField,
  matchYamlField,
  readYamlValue,
  setYamlField,
} from "./yaml-frontmatter.mjs";

function needsDescriptionCleanup(val) {
  return (
    val.includes("**") ||
    val.includes("\\n") ||
    /Status:/i.test(val) ||
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
  return fm.replace(/^completedDate:\s*.+$/m, (line) => {
    const val = readYamlValue(line.replace(/^completedDate:\s*/, ""));
    return `completedDate: ${JSON.stringify(val.replace(/\\n.*/, "").trim())}`;
  });
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
  if (!status || /^status:/m.test(fm)) return fm;
  return setYamlField(fm, "status", status);
}

function syncCompletedDateField(fm, body) {
  const completed =
    extractMarkdownField(fm, "Completed") ??
    extractMarkdownField(body.slice(0, 500), "Completed");
  if (!completed || /^completedDate:/m.test(fm)) return fm;
  return setYamlField(fm, "completedDate", completed);
}

export function fixFrontmatter(fm, body) {
  const titleMatch = fm.match(/^title:\s*(.+)$/m);
  const title = readYamlValue(titleMatch?.[1] ?? "Untitled");

  let out = fixYamlDescriptions(fm, title);
  out = normalizeCompletedDateLine(out);
  out = syncStatusField(out, body);
  out = syncCompletedDateField(out, body);
  return out;
}
