import {
  ChangelogLine,
  collapseWhitespace,
  findDateDelimiterIndex,
  findFirstDigitIndex,
  isDecimalDigits,
  isHexCommitLabel,
  isMilestoneMarker,
  isSemverChar,
  splitLines,
  takeWrappedMarkdownLink,
} from "./changelog-text";
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

function readSemverTriple(
  version: string,
): readonly [major: number, minor: number, patch: number] | null {
  const parts = version.split(".");
  if (parts.length !== 3) return null;
  const majorStr = parts.at(0) ?? "";
  const minorStr = parts.at(1) ?? "";
  const patchStr = parts.at(2) ?? "";
  if (!isDecimalDigits(majorStr)) return null;
  if (!isDecimalDigits(minorStr)) return null;
  if (!isDecimalDigits(patchStr)) return null;
  return [Number(majorStr), Number(minorStr), Number(patchStr)];
}

export function parseReleaseType(version: string): ReleaseType {
  const triple = readSemverTriple(version);
  if (!triple) return "patch";
  const [major, minor, patch] = triple;
  if (patch > 0) return "patch";
  if (minor > 0) return "minor";
  if (major > 0) return "major";
  return "patch";
}

function extractSemver(text: string): string | null {
  const start = findFirstDigitIndex(text);
  if (start === -1) return null;
  let end = start;
  while (end < text.length && isSemverChar(text.charAt(end))) end += 1;
  const candidate = text.slice(start, end);
  const parts = candidate.split(".");
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && isDecimalDigits(part))) return null;
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
  const dash = findDateDelimiterIndex(text);
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

function issueNumberFromLabel(label: string): number | null {
  if (!label.startsWith("#")) return null;
  const digits = label.slice(1);
  if (!isDecimalDigits(digits)) return null;
  return Number(digits);
}

function parseIssueLink(body: ChangelogLine): IssueRef | null {
  let remaining = body.text;
  while (remaining.length > 0) {
    const link = takeWrappedMarkdownLink(remaining);
    if (!link) return null;
    const number = issueNumberFromLabel(link.label);
    if (number !== null) return { number, url: link.url };
    remaining = link.after;
  }
  return null;
}

function parseCommitLink(body: ChangelogLine): CommitRef | null {
  let found: CommitRef | null = null;
  let remaining = body.text;
  while (true) {
    const link = takeWrappedMarkdownLink(remaining);
    if (!link) break;
    if (isHexCommitLabel(link.label)) {
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
    text = collapseWhitespace(`${link.before}${link.after}`);
  }
  return new ChangelogLine(text);
}

function stripMilestoneMarkers(body: ChangelogLine): ChangelogLine {
  let text = body.text;
  let cursor = 0;
  let built = "";
  while (cursor < text.length) {
    const start = text.indexOf("(m", cursor);
    if (start === -1) {
      built += text.slice(cursor);
      break;
    }
    built += text.slice(cursor, start);
    const end = text.indexOf(")", start);
    if (end === -1) {
      built += text.slice(start);
      break;
    }
    const marker = text.slice(start + 2, end);
    if (isMilestoneMarker(marker)) {
      built += " ";
      cursor = end + 1;
      continue;
    }
    built += "(m";
    cursor = start + 2;
  }
  return new ChangelogLine(collapseWhitespace(built));
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

  return highlights;
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

function releaseHeaderFromLine(line: ChangelogLine): MutableRelease | null {
  if (!line.startsWith("## ") || line.includes("[Unreleased]")) return null;
  const version = extractSemver(line.text);
  if (!version) return null;
  return {
    version,
    date: extractReleaseDate(line.text),
    type: parseReleaseType(version),
    summary: null,
    sections: [],
  };
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

  for (const raw of splitLines(content)) {
    const line = new ChangelogLine(raw).trimmed();

    if (isSkippableHeader(line)) {
      flushRelease(releases, current);
      current = null;
      section = null;
      continue;
    }

    const nextRelease = releaseHeaderFromLine(line);
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
): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const section of release.sections) {
    counts.set(section.title, section.items.length);
  }
  return counts;
}
