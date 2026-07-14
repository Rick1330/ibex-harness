import { ChangelogLine, splitChangelogLines } from "./changelog-line";
import {
  classifyChangePriority,
  selectHighlights,
} from "./highlight-ranking";
import type {
  ChangeItem,
  ReleaseEntry,
  ReleaseSection,
  ReleaseType,
} from "./types";

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

function readSemverTriple(
  version: string,
): readonly [major: number, minor: number, patch: number] | null {
  const parts = version.split(".");
  if (parts.length !== 3) return null;
  const majorStr = parts.at(0) ?? "";
  const minorStr = parts.at(1) ?? "";
  const patchStr = parts.at(2) ?? "";
  if (!new ChangelogLine(majorStr).isDecimalDigits()) return null;
  if (!new ChangelogLine(minorStr).isDecimalDigits()) return null;
  if (!new ChangelogLine(patchStr).isDecimalDigits()) return null;
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

function extractSemver(line: ChangelogLine): string | null {
  const start = line.findFirstDigitIndex();
  if (start === -1) return null;
  let end = start;
  while (end < line.text.length) {
    const ch = line.text.charAt(end);
    const digitLine = new ChangelogLine(ch);
    if (!digitLine.isDecimalDigits() && ch !== ".") break;
    end += 1;
  }
  const candidate = line.text.slice(start, end);
  const parts = candidate.split(".");
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && new ChangelogLine(part).isDecimalDigits())) {
    return null;
  }
  return candidate;
}

function normalizeDate(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "YYYY-MM-DD") return null;
  return trimmed;
}

function extractReleaseDate(line: ChangelogLine): string | null {
  const open = line.text.lastIndexOf("(");
  const close = line.text.lastIndexOf(")");
  if (open !== -1 && close > open) {
    return normalizeDate(line.text.slice(open + 1, close));
  }
  const emDash = line.text.indexOf("— ");
  const dash = emDash === -1 ? line.text.indexOf("- ") : emDash;
  if (dash === -1) return null;
  return normalizeDate(line.text.slice(dash + 1).trim());
}

function shouldIgnoreItem(body: ChangelogLine): boolean {
  const normalized = body.text.toLowerCase();
  return (
    normalized === "_tbd_" ||
    normalized === "(example)" ||
    normalized.startsWith("(example) ")
  );
}

function parseIssueLink(body: ChangelogLine): IssueRef | null {
  let remaining = body;
  while (!remaining.isEmpty()) {
    const link = remaining.takeWrappedMarkdownLink();
    if (!link) return null;
    const number = new ChangelogLine(link.label).issueNumberFromHashLabel();
    if (number !== null) return { number, url: link.url };
    remaining = new ChangelogLine(link.after);
  }
  return null;
}

function parseCommitLink(body: ChangelogLine): CommitRef | null {
  let found: CommitRef | null = null;
  let remaining = body;
  let link = remaining.takeWrappedMarkdownLink();
  while (link) {
    if (new ChangelogLine(link.label).isHexCommitLabel()) {
      found = { sha: link.label, url: link.url };
    }
    remaining = new ChangelogLine(link.after);
    link = remaining.takeWrappedMarkdownLink();
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

function buildChangeItem(body: ChangelogLine): ChangeItem | null {
  if (body.isEmpty() || shouldIgnoreItem(body)) return null;

  const issue = parseIssueLink(body);
  const commit = parseCommitLink(body);
  const scoped = parseScope(body);
  const description = scoped.rest.stripMarkdownLinks().stripMilestoneMarkers().text;
  if (!description) return null;

  return {
    scope: scoped.scope,
    description,
    issueNumber: issue?.number ?? null,
    issueUrl: issue?.url ?? null,
    commitSha: commit?.sha ?? null,
    commitUrl: commit?.url ?? null,
    priority: classifyChangePriority(scoped.scope),
  };
}

export function parseChangeItem(line: string): ChangeItem | null {
  const body = new ChangelogLine(line).trimmed().bulletBody();
  if (!body) return null;
  return buildChangeItem(body);
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
  const version = extractSemver(line);
  if (!version) return null;
  return {
    version,
    date: extractReleaseDate(line),
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

  for (const raw of splitChangelogLines(content)) {
    const line = raw.trimmed();

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
