import fs from "node:fs";
import path from "node:path";

import type {
  ChangeItem,
  ChangePriority,
  ReleaseEntry,
  ReleaseSection,
  ReleaseType,
} from "./types";

const VERSION_RE = /(\d+\.\d+\.\d+)/;
const DATE_PAREN_RE = /\(([^)]+)\)/;
const DATE_DASH_RE = /[-—]\s+(.+)$/;
const SECTION_HEADER = /^###\s+(.+)$/;
const BULLET_PREFIX = /^[-*]\s+/;

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
const HIGHLIGHT_CAP = 5;
const DOCS_HIGHLIGHT_CAP = 2;

const ISSUE_LINK_RE = /\(\[#(\d+)\]\(([^)]+)\)\)/;
const COMMIT_LINK_RE = /\(\[([a-f0-9]{7,40})\]\(([^)]+)\)\)/gi;
const SCOPE_RE = /^\*\*([^*]+):\*\*\s*/;
const MILESTONE_RE = /\s*\(m[\d.]+(?:\.[\d.]+)*\)\s*/gi;

type MutableSection = { title: string; items: ChangeItem[] };
type MutableRelease = {
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: MutableSection[];
};

export function parseReleaseType(version: string): ReleaseType {
  const [major, minor] = version.split(".").map((part) => Number(part) || 0);
  if (major > 0) return "major";
  if (minor > 0) return "minor";
  return "patch";
}

function normalizeDate(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "YYYY-MM-DD") return null;
  return trimmed;
}

function shouldIgnoreItem(item: string): boolean {
  const normalized = item.toLowerCase();
  return (
    normalized === "_tbd_" ||
    normalized === "(example)" ||
    normalized.startsWith("(example) ")
  );
}

function isReleaseHeader(line: string): boolean {
  return line.startsWith("## ") && VERSION_RE.test(line) && !line.includes("[Unreleased]");
}

function parseReleaseHeader(line: string): MutableRelease | null {
  if (!isReleaseHeader(line)) return null;
  const versionMatch = VERSION_RE.exec(line);
  if (!versionMatch) return null;

  const version = versionMatch[1];
  const parenDate = DATE_PAREN_RE.exec(line);
  const dashDate = parenDate ? null : DATE_DASH_RE.exec(line);
  const date = normalizeDate(parenDate?.[1] ?? dashDate?.[1] ?? null);

  return {
    version,
    date,
    type: parseReleaseType(version),
    summary: null,
    sections: [],
  };
}

function stripTrailingLinks(text: string): string {
  let result = text;
  result = result.replace(ISSUE_LINK_RE, "");
  result = result.replace(COMMIT_LINK_RE, "");
  return result.replace(/\s+/g, " ").trim();
}

function parseIssueLink(text: string): { number: number; url: string } | null {
  const match = ISSUE_LINK_RE.exec(text);
  if (!match) return null;
  return { number: Number(match[1]), url: match[2] };
}

function parseCommitLink(text: string): { sha: string; url: string } | null {
  const match = COMMIT_LINK_RE.exec(text);
  COMMIT_LINK_RE.lastIndex = 0;
  if (!match) return null;
  return { sha: match[1], url: match[2] };
}

function parseScope(text: string): { scope: string | null; rest: string } {
  const match = SCOPE_RE.exec(text);
  if (!match) return { scope: null, rest: text.trim() };
  return { scope: match[1].trim(), rest: text.slice(match[0].length).trim() };
}

function cleanDescription(raw: string): string {
  const withoutLinks = stripTrailingLinks(raw);
  return withoutLinks.replace(MILESTONE_RE, " ").replace(/\s+/g, " ").trim();
}

function classifyPriority(scope: string | null): ChangePriority {
  if (scope && INTERNAL_SCOPES.has(scope)) return "internal";
  return "standard";
}

export function parseChangeItem(line: string): ChangeItem | null {
  const bulletMatch = BULLET_PREFIX.exec(line);
  if (!bulletMatch) return null;

  const raw = line.slice(bulletMatch[0].length).trim();
  if (!raw || shouldIgnoreItem(raw)) return null;

  const issue = parseIssueLink(raw);
  const commit = parseCommitLink(raw);
  const { scope, rest } = parseScope(raw);
  const description = cleanDescription(rest);

  if (!description) return null;

  return {
    scope,
    description,
    issueNumber: issue?.number ?? null,
    issueUrl: issue?.url ?? null,
    commitSha: commit?.sha ?? null,
    commitUrl: commit?.url ?? null,
    priority: classifyPriority(scope),
  };
}

function scoreHighlight(item: ChangeItem): number {
  let score = 0;
  if (item.issueNumber !== null) score += 10;
  if (item.scope && USER_FACING_SCOPES.has(item.scope)) score += 5;
  if (item.priority === "internal") score -= 8;
  if (item.scope === "docs") score -= 2;
  return score;
}

function shouldSkipForCaps(
  item: ChangeItem,
  internalCounts: Map<string, number>,
  docsCount: number,
): boolean {
  if (item.priority === "internal" && item.scope) {
    if ((internalCounts.get(item.scope) ?? 0) >= 1) return true;
  }
  if (item.scope === "docs" && docsCount >= DOCS_HIGHLIGHT_CAP) return true;
  return false;
}

function recordCapUsage(
  item: ChangeItem,
  internalCounts: Map<string, number>,
): number {
  if (item.priority === "internal" && item.scope) {
    internalCounts.set(item.scope, (internalCounts.get(item.scope) ?? 0) + 1);
  }
  return item.scope === "docs" ? 1 : 0;
}

function selectHighlights(items: ChangeItem[]): ChangeItem[] {
  if (items.length === 0) return [];

  const ranked = [...items].sort(
    (a, b) => scoreHighlight(b) - scoreHighlight(a),
  );

  const highlights: ChangeItem[] = [];
  const internalCounts = new Map<string, number>();
  let docsCount = 0;

  for (const item of ranked) {
    if (highlights.length >= HIGHLIGHT_CAP) break;
    if (shouldSkipForCaps(item, internalCounts, docsCount)) continue;
    docsCount += recordCapUsage(item, internalCounts);
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

function isSkippableHeader(line: string): boolean {
  return (
    line.startsWith("## [Unreleased]") || line === "## Changelog discipline"
  );
}

function applyLineToRelease(
  line: string,
  current: MutableRelease,
  section: MutableSection | null,
): MutableSection | null {
  const sectionMatch = SECTION_HEADER.exec(line);
  if (sectionMatch) {
    const next = { title: sectionMatch[1], items: [] as ChangeItem[] };
    current.sections.push(next);
    return next;
  }

  const item = parseChangeItem(line);
  if (item && section) {
    section.items.push(item);
    return section;
  }

  if (!line || line.startsWith("---")) return section;
  if (!section && !current.summary) current.summary = line;
  return section;
}

export function parseChangelogContent(content: string): ReleaseEntry[] {
  const releases: ReleaseEntry[] = [];
  let current: MutableRelease | null = null;
  let section: MutableSection | null = null;

  for (const raw of content.split(/\r?\n/)) {
    const line = raw.trim();

    if (isSkippableHeader(line)) {
      flushRelease(releases, current);
      current = null;
      section = null;
      continue;
    }

    const nextRelease = parseReleaseHeader(line);
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

export function readReleasesFromChangelog(
  changelogPath?: string,
): ReleaseEntry[] {
  const resolved =
    changelogPath ?? path.resolve(process.cwd(), "../CHANGELOG.md");
  const content = fs.readFileSync(resolved, "utf8");
  return parseChangelogContent(content);
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
