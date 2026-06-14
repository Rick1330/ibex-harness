/** Shared YAML frontmatter helpers for roadmap migration scripts. */

export const YAML_FIELD_KEYS = new Set([
  "description",
  "summary",
  "status",
  "completedDate",
  "title",
  "fullTitle",
]);

const YAML_LINE_PATTERNS = {
  description: /^description:\s*.+$/m,
  summary: /^summary:\s*.+$/m,
  status: /^status:\s*.+$/m,
  completedDate: /^completedDate:\s*.+$/m,
  title: /^title:\s*.+$/m,
  fullTitle: /^fullTitle:\s*.+$/m,
};

const YAML_VALUE_PATTERNS = {
  description: /^description:\s*(.+)$/m,
  summary: /^summary:\s*(.+)$/m,
  status: /^status:\s*(.+)$/m,
  completedDate: /^completedDate:\s*(.+)$/m,
  title: /^title:\s*(.+)$/m,
  fullTitle: /^fullTitle:\s*(.+)$/m,
};

export const MARKDOWN_FIELD_PATTERNS = {
  Status: /\*\*Status:\*\*\s*([^\n*]+)/i,
  Completed: /\*\*Completed:\*\*\s*([^\n*]+)/i,
  "Estimated duration": /\*\*Estimated duration:\*\*\s*([^\n*]+)/i,
  "Depends on": /\*\*Depends on:\*\*\s*([^\n*]+)/i,
  "Current milestone": /\*\*Current milestone:\*\*\s*([^\n*]+)/i,
};

export function readYamlValue(raw) {
  const trimmed = raw.trim();
  if (trimmed.startsWith('"') || trimmed.startsWith("'")) {
    try {
      return JSON.parse(trimmed.startsWith('"') ? trimmed : `"${trimmed.slice(1, -1)}"`);
    } catch {
      return trimmed.replace(/^"|"$/g, "");
    }
  }
  return trimmed.replace(/^"|"$/g, "");
}

export function extractMarkdownField(text, label) {
  const pattern = MARKDOWN_FIELD_PATTERNS[label];
  if (!pattern) return undefined;
  return text.match(pattern)?.[1]?.trim();
}

export function setYamlField(fm, key, value) {
  if (!YAML_FIELD_KEYS.has(key)) {
    throw new Error(`Invalid YAML field key: ${key}`);
  }
  const re = YAML_LINE_PATTERNS[key];
  const line = `${key}: ${JSON.stringify(value)}`;
  if (re.test(fm)) return fm.replace(re, line);
  return `${fm}\n${line}`;
}

export function matchYamlField(fm, key) {
  if (!YAML_FIELD_KEYS.has(key)) {
    throw new Error(`Invalid YAML field key: ${key}`);
  }
  return fm.match(YAML_VALUE_PATTERNS[key]);
}
