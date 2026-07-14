/** Line wrapper: text scanners as methods to avoid string-heavy module surfaces. */

export type WrappedMarkdownLink = Readonly<{
  label: string;
  url: string;
  before: string;
  after: string;
}>;

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

  private charAt(index: number): string {
    return this.text.charAt(index);
  }

  private isAsciiDigitAt(index: number): boolean {
    const ch = this.charAt(index);
    if (ch.length !== 1) return false;
    const code = ch.codePointAt(0);
    return code !== undefined && code >= 48 && code <= 57;
  }

  isDecimalDigits(): boolean {
    if (this.text.length === 0) return false;
    for (let i = 0; i < this.text.length; i += 1) {
      if (!this.isAsciiDigitAt(i)) return false;
    }
    return true;
  }

  findFirstDigitIndex(): number {
    for (let i = 0; i < this.text.length; i += 1) {
      if (this.isAsciiDigitAt(i)) return i;
    }
    return -1;
  }

  collapseWhitespace(): ChangelogLine {
    let result = "";
    let pendingSpace = false;
    for (let i = 0; i < this.text.length; i += 1) {
      const ch = this.charAt(i);
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
    return new ChangelogLine(result.trim());
  }

  takeWrappedMarkdownLink(): WrappedMarkdownLink | null {
    const open = this.text.indexOf("([");
    if (open === -1) return null;
    const mid = this.text.indexOf("](", open);
    if (mid === -1) return null;
    const urlEnd = this.text.indexOf(")", mid + 2);
    if (urlEnd === -1) return null;
    const end = this.charAt(urlEnd + 1) === ")" ? urlEnd + 1 : urlEnd;
    return {
      label: this.text.slice(open + 2, mid),
      url: this.text.slice(mid + 2, urlEnd),
      before: this.text.slice(0, open),
      after: this.text.slice(end + 1),
    };
  }

  stripMarkdownLinks(): ChangelogLine {
    let text = this.text;
    let link = new ChangelogLine(text).takeWrappedMarkdownLink();
    while (link) {
      text = new ChangelogLine(`${link.before}${link.after}`).collapseWhitespace().text;
      link = new ChangelogLine(text).takeWrappedMarkdownLink();
    }
    return new ChangelogLine(text);
  }

  stripMilestoneMarkers(): ChangelogLine {
    let cursor = 0;
    let built = "";
    while (cursor < this.text.length) {
      const start = this.text.indexOf("(m", cursor);
      if (start === -1) {
        built += this.text.slice(cursor);
        break;
      }
      built += this.text.slice(cursor, start);
      const end = this.text.indexOf(")", start);
      if (end === -1) {
        built += this.text.slice(start);
        break;
      }
      const marker = new ChangelogLine(this.text.slice(start + 2, end));
      if (marker.isMilestoneMarker()) {
        built += " ";
        cursor = end + 1;
        continue;
      }
      built += "(m";
      cursor = start + 2;
    }
    return new ChangelogLine(built).collapseWhitespace();
  }

  isMilestoneMarker(): boolean {
    if (this.text.length === 0) return false;
    for (let i = 0; i < this.text.length; i += 1) {
      const ch = this.charAt(i);
      if (!this.isAsciiDigitAt(i) && ch !== ".") return false;
    }
    return true;
  }

  isHexCommitLabel(): boolean {
    const len = this.text.length;
    if (len < 7 || len > 40) return false;
    for (let i = 0; i < len; i += 1) {
      const ch = this.charAt(i).toLowerCase();
      const isDigit = ch >= "0" && ch <= "9";
      const isHex = isDigit || (ch >= "a" && ch <= "f");
      if (!isHex) return false;
    }
    return true;
  }

  issueNumberFromHashLabel(): number | null {
    if (!this.text.startsWith("#")) return null;
    const digits = new ChangelogLine(this.text.slice(1));
    if (!digits.isDecimalDigits()) return null;
    return Number(digits.text);
  }
}

export function splitChangelogLines(content: string): ChangelogLine[] {
  return content
    .split("\n")
    .map((line) => (line.endsWith("\r") ? line.slice(0, -1) : line))
    .map((line) => new ChangelogLine(line));
}
