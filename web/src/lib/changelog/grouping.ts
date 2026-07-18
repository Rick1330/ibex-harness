import type { ReleaseEntry } from "@/lib/changelog/types";

export type ChangelogQuarter = 1 | 2 | 3 | 4;

export type ChangelogNavGroup = Readonly<{
  year: number;
  quarters: ReadonlyArray<{
    quarter: ChangelogQuarter;
    label: string;
    anchor: string;
    count: number;
  }>;
}>;

const SECTION_LABELS: ReadonlyArray<Readonly<{ match: string; label: string }>> =
  [
    { match: "breaking", label: "Breaking" },
    { match: "bug", label: "Fixed" },
    { match: "fix", label: "Fixed" },
    { match: "feature", label: "Added" },
    { match: "added", label: "Added" },
    { match: "deprecat", label: "Deprecated" },
    { match: "security", label: "Security" },
    { match: "change", label: "Changed" },
    { match: "performance", label: "Changed" },
    { match: "refactor", label: "Changed" },
  ];

export function releaseYear(date: string | null): number | null {
  if (!date) return null;
  const year = new Date(date).getUTCFullYear();
  return Number.isFinite(year) ? year : null;
}

export function releaseQuarter(date: string | null): ChangelogQuarter | null {
  if (!date) return null;
  const month = new Date(date).getUTCMonth();
  if (!Number.isFinite(month)) return null;
  return (Math.floor(month / 3) + 1) as ChangelogQuarter;
}

export function quarterAnchor(year: number, quarter: ChangelogQuarter): string {
  return `y${year}-q${quarter}`;
}

export function isNewRelease(date: string | null, now = new Date()): boolean {
  if (!date) return false;
  const published = new Date(date);
  if (!Number.isFinite(published.getTime())) return false;
  const ageMs = now.getTime() - published.getTime();
  return ageMs >= 0 && ageMs < 14 * 24 * 60 * 60 * 1000;
}

/** Map conventional-changelog section titles → editorial H4 labels. */
export function editorialSectionLabel(title: string): string {
  const normalized = title.toLowerCase();
  for (const rule of SECTION_LABELS) {
    if (normalized.includes(rule.match)) return rule.label;
  }
  return title;
}

type QuarterMeta = { count: number };

function tallyRelease(
  map: Map<number, Map<ChangelogQuarter, QuarterMeta>>,
  release: ReleaseEntry,
): void {
  const year = releaseYear(release.date);
  const quarter = releaseQuarter(release.date);
  if (year === null || quarter === null) return;

  let yearMap = map.get(year);
  if (!yearMap) {
    yearMap = new Map();
    map.set(year, yearMap);
  }
  const existing = yearMap.get(quarter);
  if (existing) {
    existing.count += 1;
    return;
  }
  yearMap.set(quarter, { count: 1 });
}

function navGroupFromYear(
  year: number,
  quarters: Map<ChangelogQuarter, QuarterMeta>,
): ChangelogNavGroup {
  return {
    year,
    quarters: [...quarters.entries()]
      .sort(([a], [b]) => b - a)
      .map(([quarter, meta]) => ({
        quarter,
        label: `Q${quarter}`,
        anchor: quarterAnchor(year, quarter),
        count: meta.count,
      })),
  };
}

/** Build year → quarter nav from releases (newest first). */
export function buildChangelogNav(
  releases: ReadonlyArray<ReleaseEntry>,
): ChangelogNavGroup[] {
  const map = new Map<number, Map<ChangelogQuarter, QuarterMeta>>();
  for (const release of releases) tallyRelease(map, release);

  return [...map.entries()]
    .sort(([a], [b]) => b - a)
    .map(([year, quarters]) => navGroupFromYear(year, quarters));
}

export function formatChangelogDate(date: string | null): string {
  if (!date) return "Undated";
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });
}
