/** Shared YAML frontmatter helpers for roadmap migration scripts. */

import {
  extractBoldField,
  findYamlLine,
  readYamlLineValue,
} from "./text-utils.mjs";

export const YAML_FIELD_KEYS = new Set([
  "description",
  "summary",
  "status",
  "completedDate",
  "title",
  "fullTitle",
]);

const MARKDOWN_FIELD_LABELS = [
  "Status",
  "Completed",
  "Estimated duration",
  "Depends on",
  "Current milestone",
];

export function readYamlValue(raw) {
  const trimmed = raw.trim();
  if (trimmed.startsWith('"')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed.slice(1, -1);
    }
  }
  if (trimmed.startsWith("'")) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function extractMarkdownField(text, label) {
  if (!MARKDOWN_FIELD_LABELS.includes(label)) return undefined;
  return extractBoldField(text, label);
}

export function setYamlField(fm, key, value) {
  if (!YAML_FIELD_KEYS.has(key)) {
    throw new Error(`Invalid YAML field key: ${key}`);
  }

  const prefix = `${key}:`;
  const newLine = `${key}: ${JSON.stringify(value)}`;
  const lines = fm.split("\n");
  let replaced = false;

  const updated = lines.map((line) => {
    if (line.startsWith(prefix)) {
      replaced = true;
      return newLine;
    }
    return line;
  });

  if (!replaced) return `${fm}\n${newLine}`;
  return updated.join("\n");
}

export function matchYamlField(fm, key) {
  if (!YAML_FIELD_KEYS.has(key)) {
    throw new Error(`Invalid YAML field key: ${key}`);
  }

  const line = findYamlLine(fm, key);
  if (!line) return null;

  const raw = readYamlLineValue(line, key);
  if (raw === undefined) return null;
  return [line, readYamlValue(raw)];
}
