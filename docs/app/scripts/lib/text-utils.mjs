/** String helpers without backtracking-prone regex (Sonar S5852). */

export function stripMarkdownLinks(text) {
  let result = "";
  let index = 0;

  while (index < text.length) {
    if (text[index] === "[") {
      const bracketEnd = text.indexOf("]", index + 1);
      if (bracketEnd !== -1 && text[bracketEnd + 1] === "(") {
        const parenEnd = text.indexOf(")", bracketEnd + 2);
        if (parenEnd !== -1) {
          result += text.slice(index + 1, bracketEnd);
          index = parenEnd + 1;
          continue;
        }
      }
    }
    result += text[index];
    index += 1;
  }

  return result;
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

export function extractSectionAfterHeading(content, heading) {
  const needle = `## ${heading}`;
  const startIndex = content.toLowerCase().indexOf(needle.toLowerCase());
  if (startIndex === -1) return undefined;

  let start = content.indexOf("\n", startIndex);
  if (start === -1) return undefined;
  start += 1;

  while (content[start] === "\n") start += 1;

  const endMarkers = ["\n## ", "\n---"];
  let end = content.length;
  for (const marker of endMarkers) {
    const markerIndex = content.indexOf(marker, start);
    if (markerIndex !== -1 && markerIndex < end) end = markerIndex;
  }

  return content.slice(start, end).trim();
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
    if (char === ")") {
      if (depth > 0) depth -= 1;
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
