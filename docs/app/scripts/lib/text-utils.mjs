/** String helpers without backtracking-prone regex (Sonar S5852). */

import { rewriteAllMarkdownLinks } from "./markdown-link-rewrite.mjs";

export function stripMarkdownLinks(text) {
  return rewriteAllMarkdownLinks(text, (link) => link.text);
}

export function extractH1Title(content) {
  for (const line of content.split("\n")) {
    if (line.startsWith("# ")) return line.slice(2).trim();
  }
  return undefined;
}

export function extractBoldField(content, label) {
  const marker = `**${label}:**`;
  const lower = content.toLowerCase();
  const markerLower = marker.toLowerCase();
  const index = lower.indexOf(markerLower);
  if (index === -1) return undefined;

  const start = index + marker.length;
  const lineEnd = content.indexOf("\n", start);
  const raw = lineEnd === -1 ? content.slice(start) : content.slice(start, lineEnd);
  return raw.trim();
}

function endOfSection(content, start) {
  const endMarkers = ["\n## ", "\n---"];
  let end = content.length;
  for (const marker of endMarkers) {
    const markerIndex = content.indexOf(marker, start);
    if (markerIndex !== -1 && markerIndex < end) end = markerIndex;
  }
  return end;
}

export function extractSectionAfterHeading(content, heading) {
  const needle = `## ${heading}`;
  const startIndex = content.toLowerCase().indexOf(needle.toLowerCase());
  if (startIndex === -1) return undefined;

  let start = content.indexOf("\n", startIndex);
  if (start === -1) return undefined;
  start += 1;

  while (content[start] === "\n") start += 1;

  return content.slice(start, endOfSection(content, start)).trim();
}

export function findYamlLine(fm, key) {
  const prefix = `${key}:`;
  for (const line of fm.split("\n")) {
    if (line.startsWith(prefix)) return line;
  }
  return undefined;
}

export function readYamlLineValue(line, key) {
  const prefix = `${key}:`;
  if (!line.startsWith(prefix)) return undefined;
  return line.slice(prefix.length).trim();
}

export function stripParenthetical(text) {
  let out = "";
  let depth = 0;

  for (const char of text) {
    if (char === "(") {
      depth += 1;
      continue;
    }
    if (char === ")" && depth > 0) {
      depth -= 1;
      continue;
    }
    if (depth === 0) out += char;
  }

  return out.trim();
}

export function stripAfterDelimiter(text, delimiter) {
  const index = text.indexOf(delimiter);
  return index === -1 ? text.trim() : text.slice(0, index).trim();
}
