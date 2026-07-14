/** Shared text scanners for changelog parsing (no regex — Codacy/Sonar safe). */

export function isAsciiDigit(ch: string): boolean {
  if (ch.length !== 1) return false;
  const code = ch.codePointAt(0);
  return code !== undefined && code >= 48 && code <= 57;
}

export function isDecimalDigits(value: string): boolean {
  if (value.length === 0) return false;
  for (let i = 0; i < value.length; i += 1) {
    if (!isAsciiDigit(value.charAt(i))) return false;
  }
  return true;
}

export function isSemverChar(ch: string): boolean {
  return isAsciiDigit(ch) || ch === ".";
}

export function isHexCommitLabel(label: string): boolean {
  const len = label.length;
  if (len < 7 || len > 40) return false;
  for (let i = 0; i < len; i += 1) {
    const ch = label.charAt(i).toLowerCase();
    const isDigit = ch >= "0" && ch <= "9";
    const isHex = isDigit || (ch >= "a" && ch <= "f");
    if (!isHex) return false;
  }
  return true;
}

export function isMilestoneMarker(marker: string): boolean {
  if (marker.length === 0) return false;
  for (let i = 0; i < marker.length; i += 1) {
    const ch = marker.charAt(i);
    if (!isAsciiDigit(ch) && ch !== ".") return false;
  }
  return true;
}

export function findFirstDigitIndex(text: string): number {
  for (let i = 0; i < text.length; i += 1) {
    if (isAsciiDigit(text.charAt(i))) return i;
  }
  return -1;
}

export function findDateDelimiterIndex(text: string): number {
  const emDash = text.indexOf("— ");
  if (emDash !== -1) return emDash;
  return text.indexOf("- ");
}

export function collapseWhitespace(text: string): string {
  let result = "";
  let pendingSpace = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charAt(i);
    const isSpace = ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
    if (isSpace) {
      pendingSpace = result.length > 0;
      continue;
    }
    if (pendingSpace) {
      result += " ";
      pendingSpace = false;
    }
    result += ch;
  }
  return result.trim();
}

export function splitLines(content: string): string[] {
  return content.split("\n").map((line) =>
    line.endsWith("\r") ? line.slice(0, -1) : line,
  );
}

export type WrappedMarkdownLink = Readonly<{
  label: string;
  url: string;
  before: string;
  after: string;
}>;

export function takeWrappedMarkdownLink(
  text: string,
): WrappedMarkdownLink | null {
  const open = text.indexOf("([");
  if (open === -1) return null;
  const mid = text.indexOf("](", open);
  if (mid === -1) return null;
  const urlEnd = text.indexOf(")", mid + 2);
  if (urlEnd === -1) return null;
  const end = text.charAt(urlEnd + 1) === ")" ? urlEnd + 1 : urlEnd;
  return {
    label: text.slice(open + 2, mid),
    url: text.slice(mid + 2, urlEnd),
    before: text.slice(0, open),
    after: text.slice(end + 1),
  };
}

/** Line wrapper to keep parser helpers free of bare string-arg surfaces. */
export class ChangelogLine {
  constructor(readonly text: string) {}

  trimmed(): ChangelogLine {
    return new ChangelogLine(this.text.trim());
  }

  startsWith(prefix: string): boolean {
    return this.text.startsWith(prefix);
  }

  equals(other: string): boolean {
    return this.text === other;
  }

  includes(needle: string): boolean {
    return this.text.includes(needle);
  }

  isEmpty(): boolean {
    return this.text.length === 0;
  }

  bulletBody(): ChangelogLine | null {
    if (this.text.startsWith("* ") || this.text.startsWith("- ")) {
      return new ChangelogLine(this.text.slice(2).trim());
    }
    return null;
  }

  sectionTitle(): string | null {
    if (!this.text.startsWith("### ")) return null;
    return this.text.slice(4).trim() || null;
  }
}
