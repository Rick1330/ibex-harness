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
  if (normalized.includes("breaking")) return "Breaking";
  if (normalized.includes("bug") || normalized.includes("fix")) return "Fixed";
  if (normalized.includes("feature") || normalized.includes("added")) {
    return "Added";
  }
  if (normalized.includes("deprecat")) return "Deprecated";
  if (normalized.includes("security")) return "Security";
  if (
    normalized.includes("change") ||
    normalized.includes("performance") ||
    normalized.includes("refactor")
  ) {
    return "Changed";
  }
  return title;
}

/** Build year → quarter nav from releases (newest first). */
export function buildChangelogNav(
  releases: ReadonlyArray<ReleaseEntry>,
): ChangelogNavGroup[] {
  const map = new Map<
    number,
    Map<ChangelogQuarter, { count: number; firstVersion: string }>
  >();

  for (const release of releases) {
    const year = releaseYear(release.date);
    const quarter = releaseQuarter(release.date);
    if (year === null || quarter === null) continue;

    let yearMap = map.get(year);
    if (!yearMap) {
      yearMap = new Map();
      map.set(year, yearMap);
    }
    const existing = yearMap.get(quarter);
    if (existing) {
      existing.count += 1;
    } else {
      yearMap.set(quarter, { count: 1, firstVersion: release.version });
    }
  }

  return [...map.entries()]
    .sort(([a], [b]) => b - a)
    .map(([year, quarters]) => ({
      year,
      quarters: [...quarters.entries()]
        .sort(([a], [b]) => b - a)
        .map(([quarter, meta]) => ({
          quarter,
          label: `Q${quarter}`,
          anchor: quarterAnchor(year, quarter),
          count: meta.count,
        })),
    }));
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
