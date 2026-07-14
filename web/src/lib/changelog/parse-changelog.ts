import type {
  ChangeItem,
  ChangePriority,
  ReleaseEntry,
  ReleaseSection,
  ReleaseType,
} from "./types";

const HIGHLIGHT_CAP = 5;
const DOCS_HIGHLIGHT_CAP = 2;

const INTERNAL_SCOPES = new Set(["ci", "test", "dx", "docker"]);
const USER_FACING_SCOPES = new Set([
  "auth",
  "proxy",
  "db",
  "web",
  "bench",
  "infra",
  "docs",
]);

type MutableSection = { title: string; items: ChangeItem[] };
type MutableRelease = {
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: MutableSection[];
};

type IssueRef = Readonly<{ number: number; url: string }>;
type CommitRef = Readonly<{ sha: string; url: string }>;
type CapState = {
  internalCounts: Map<string, number>;
  docsCount: number;
};

/** Line wrapper to keep parser helpers free of bare string-arg surfaces. */
class ChangelogLine {
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

  releaseHeader(): MutableRelease | null {
    if (!this.startsWith("## ") || this.includes("[Unreleased]")) return null;
    const version = extractSemver(this.text);
    if (!version) return null;
    return {
      version,
      date: extractReleaseDate(this.text),
      type: parseReleaseType(version),
      summary: null,
      sections: [],
    };
  }
}

export function parseReleaseType(version: string): ReleaseType {
  const parts = version.split(".");
  const major = Number(parts[0]) || 0;
  const minor = Number(parts[1]) || 0;
  if (major > 0) return "major";
  if (minor > 0) return "minor";
  return "patch";
}

function extractSemver(text: string): string | null {
  const start = text.search(/\d/);
  if (start === -1) return null;
  let end = start;
  while (end < text.length && /[\d.]/.test(text[end])) end += 1;
  const candidate = text.slice(start, end);
  const parts = candidate.split(".");
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && /^\d+$/.test(part))) return null;
  return candidate;
}

function normalizeDate(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "YYYY-MM-DD") return null;
  return trimmed;
}

function extractReleaseDate(text: string): string | null {
  const open = text.lastIndexOf("(");
  const close = text.lastIndexOf(")");
  if (open !== -1 && close > open) {
    return normalizeDate(text.slice(open + 1, close));
  }
  const dash = text.search(/[-—]\s/);
  if (dash === -1) return null;
  return normalizeDate(text.slice(dash + 1).trim());
}

function shouldIgnoreItem(body: ChangelogLine): boolean {
  const normalized = body.text.toLowerCase();
  return (
    normalized === "_tbd_" ||
    normalized === "(example)" ||
    normalized.startsWith("(example) ")
  );
}

function takeWrappedMarkdownLink(
  text: string,
): { label: string; url: string; before: string; after: string } | null {
  const open = text.indexOf("([");
  if (open === -1) return null;
  const mid = text.indexOf("](", open);
  if (mid === -1) return null;
  const urlEnd = text.indexOf(")", mid + 2);
  if (urlEnd === -1) return null;
  // Engine wraps markdown links as ([label](url)) — consume the outer ')' when present.
  const end = text[urlEnd + 1] === ")" ? urlEnd + 1 : urlEnd;
  return {
    label: text.slice(open + 2, mid),
    url: text.slice(mid + 2, urlEnd),
    before: text.slice(0, open),
    after: text.slice(end + 1),
  };
}

function parseIssueLink(body: ChangelogLine): IssueRef | null {
  let cursor = 0;
  while (cursor < body.text.length) {
    const slice = body.text.slice(cursor);
    const link = takeWrappedMarkdownLink(slice);
    if (!link) return null;
    if (link.label.startsWith("#")) {
      const digits = link.label.slice(1);
      if (/^\d+$/.test(digits)) {
        return { number: Number(digits), url: link.url };
      }
    }
    cursor += link.before.length + 1;
  }
  return null;
}

function parseCommitLink(body: ChangelogLine): CommitRef | null {
  let found: CommitRef | null = null;
  let remaining = body.text;
  while (true) {
    const link = takeWrappedMarkdownLink(remaining);
    if (!link) break;
    if (/^[a-f0-9]{7,40}$/i.test(link.label)) {
      found = { sha: link.label, url: link.url };
    }
    remaining = link.after;
  }
  return found;
}

function parseScope(body: ChangelogLine): {
  scope: string | null;
  rest: ChangelogLine;
} {
  if (!body.startsWith("**")) {
    return { scope: null, rest: body };
  }
  const close = body.text.indexOf(":**", 2);
  if (close === -1) return { scope: null, rest: body };
  const scope = body.text.slice(2, close).trim();
  return {
    scope: scope || null,
    rest: new ChangelogLine(body.text.slice(close + 3).trim()),
  };
}

function stripMarkdownLinks(body: ChangelogLine): ChangelogLine {
  let text = body.text;
  while (true) {
    const link = takeWrappedMarkdownLink(text);
    if (!link) break;
    text = `${link.before}${link.after}`.replace(/\s+/g, " ").trim();
  }
  return new ChangelogLine(text);
}

function stripMilestoneMarkers(body: ChangelogLine): ChangelogLine {
  let text = body.text;
  while (true) {
    const start = text.lastIndexOf("(m");
    if (start === -1) break;
    const end = text.indexOf(")", start);
    if (end === -1) break;
    const marker = text.slice(start + 2, end);
    if (!/^[\d.]+$/.test(marker)) break;
    text = `${text.slice(0, start)} ${text.slice(end + 1)}`
      .replace(/\s+/g, " ")
      .trim();
  }
  return new ChangelogLine(text);
}

function classifyPriority(scope: string | null): ChangePriority {
  if (scope && INTERNAL_SCOPES.has(scope)) return "internal";
  return "standard";
}

function buildChangeItem(body: ChangelogLine): ChangeItem | null {
  if (body.isEmpty() || shouldIgnoreItem(body)) return null;

  const issue = parseIssueLink(body);
  const commit = parseCommitLink(body);
  const scoped = parseScope(body);
  const description = stripMilestoneMarkers(
    stripMarkdownLinks(scoped.rest),
  ).text;
  if (!description) return null;

  return {
    scope: scoped.scope,
    description,
    issueNumber: issue?.number ?? null,
    issueUrl: issue?.url ?? null,
    commitSha: commit?.sha ?? null,
    commitUrl: commit?.url ?? null,
    priority: classifyPriority(scoped.scope),
  };
}

export function parseChangeItem(line: string): ChangeItem | null {
  const body = new ChangelogLine(line).trimmed().bulletBody();
  if (!body) return null;
  return buildChangeItem(body);
}

function scoreHighlight(item: ChangeItem): number {
  let score = 0;
  if (item.issueNumber !== null) score += 10;
  if (item.scope && USER_FACING_SCOPES.has(item.scope)) score += 5;
  if (item.priority === "internal") score -= 8;
  if (item.scope === "docs") score -= 2;
  return score;
}

function shouldSkipForCaps(item: ChangeItem, caps: CapState): boolean {
  if (item.priority === "internal" && item.scope) {
    if ((caps.internalCounts.get(item.scope) ?? 0) >= 1) return true;
  }
  return item.scope === "docs" && caps.docsCount >= DOCS_HIGHLIGHT_CAP;
}

function recordCapUsage(item: ChangeItem, caps: CapState): void {
  if (item.priority === "internal" && item.scope) {
    caps.internalCounts.set(
      item.scope,
      (caps.internalCounts.get(item.scope) ?? 0) + 1,
    );
  }
  if (item.scope === "docs") caps.docsCount += 1;
}

function selectHighlights(items: ChangeItem[]): ChangeItem[] {
  if (items.length === 0) return [];

  const ranked = [...items].sort(
    (a, b) => scoreHighlight(b) - scoreHighlight(a),
  );
  const highlights: ChangeItem[] = [];
  const caps: CapState = { internalCounts: new Map(), docsCount: 0 };

  for (const item of ranked) {
    if (highlights.length >= HIGHLIGHT_CAP) break;
    if (shouldSkipForCaps(item, caps)) continue;
    recordCapUsage(item, caps);
    highlights.push({ ...item, priority: "highlight" });
  }

  if (highlights.length > 0) return highlights;

  return ranked.slice(0, Math.min(HIGHLIGHT_CAP, ranked.length)).map((item) => ({
    ...item,
    priority: "highlight" as const,
  }));
}

function finalizeSection(section: MutableSection): ReleaseSection {
  return {
    title: section.title,
    items: section.items,
    highlights: selectHighlights(section.items),
  };
}

function flushRelease(
  list: ReleaseEntry[],
  current: MutableRelease | null,
): void {
  if (!current) return;
  list.push({
    ...current,
    sections: current.sections
      .filter((section) => section.items.length > 0)
      .map(finalizeSection),
  });
}

function isSkippableHeader(line: ChangelogLine): boolean {
  return (
    line.startsWith("## [Unreleased]") ||
    line.equals("## Changelog discipline")
  );
}

function applyLineToRelease(
  line: ChangelogLine,
  current: MutableRelease,
  section: MutableSection | null,
): MutableSection | null {
  const sectionTitle = line.sectionTitle();
  if (sectionTitle) {
    const next = { title: sectionTitle, items: [] as ChangeItem[] };
    current.sections.push(next);
    return next;
  }

  const item = parseChangeItem(line.text);
  if (item && section) {
    section.items.push(item);
    return section;
  }

  if (line.isEmpty() || line.startsWith("---")) return section;
  if (!section && !current.summary) current.summary = line.text;
  return section;
}

export function parseChangelogContent(content: string): ReleaseEntry[] {
  const releases: ReleaseEntry[] = [];
  let current: MutableRelease | null = null;
  let section: MutableSection | null = null;

  for (const raw of content.split(/\r?\n/)) {
    const line = new ChangelogLine(raw).trimmed();

    if (isSkippableHeader(line)) {
      flushRelease(releases, current);
      current = null;
      section = null;
      continue;
    }

    const nextRelease = line.releaseHeader();
    if (nextRelease) {
      flushRelease(releases, current);
      current = nextRelease;
      section = null;
      continue;
    }

    if (!current) continue;
    section = applyLineToRelease(line, current, section);
  }

  flushRelease(releases, current);
  return releases;
}

export function collectScopes(release: ReleaseEntry): string[] {
  const scopes = new Set<string>();
  for (const section of release.sections) {
    for (const item of section.items) {
      if (item.scope) scopes.add(item.scope);
    }
  }
  return [...scopes].sort((a, b) => a.localeCompare(b));
}

export function countBySectionTitle(
  release: ReleaseEntry,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const section of release.sections) {
    counts[section.title] = section.items.length;
  }
  return counts;
}
