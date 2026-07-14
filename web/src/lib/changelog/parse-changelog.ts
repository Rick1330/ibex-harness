import { parseChangeItem } from "./change-item-parser";
import { ChangelogLine, splitChangelogLines } from "./changelog-line";
import { selectHighlights } from "./highlight-ranking";
import { releaseHeaderFromLine } from "./release-header";
import type {
  ChangeItem,
  ReleaseEntry,
  ReleaseSection,
} from "./types";

type MutableSection = { title: string; items: ChangeItem[] };
type MutableRelease = {
  version: string;
  date: string | null;
  type: ReleaseEntry["type"];
  summary: string | null;
  sections: MutableSection[];
};

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

  if (line.isEmpty() || line.startsWith("---")) return section;

  const item = parseChangeItem(line.text);
  if (item && section) {
    section.items.push(item);
    return section;
  }

  if (!section && !current.summary) current.summary = line.text;
  return section;
}

function resetReleaseState(): {
  current: MutableRelease | null;
  section: MutableSection | null;
} {
  return { current: null, section: null };
}

export function parseChangelogContent(content: string): ReleaseEntry[] {
  const releases: ReleaseEntry[] = [];
  let { current, section } = resetReleaseState();

  for (const raw of splitChangelogLines(content)) {
    const line = raw.trimmed();

    if (isSkippableHeader(line)) {
      flushRelease(releases, current);
      ({ current, section } = resetReleaseState());
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

export { parseChangeItem } from "./change-item-parser";
export { parseReleaseType } from "./release-header";
