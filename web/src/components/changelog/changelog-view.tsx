import { ChangelogEntry } from "@/components/changelog/changelog-entry";
import { ChangelogFooterStrip } from "@/components/changelog/changelog-footer-strip";
import { ChangelogYearNav } from "@/components/changelog/changelog-year-nav";
import {
  buildChangelogNav,
  quarterAnchor,
  releaseQuarter,
  releaseYear,
} from "@/lib/changelog/grouping";
import type { ReleaseEntry } from "@/lib/changelog/types";

type ChangelogViewProps = Readonly<{
  releases: ReleaseEntry[];
}>;

function firstInQuarterKeys(releases: ReleaseEntry[]): Set<string> {
  const seen = new Set<string>();
  const firsts = new Set<string>();
  for (const release of releases) {
    const year = releaseYear(release.date);
    const quarter = releaseQuarter(release.date);
    if (year === null || quarter === null) continue;
    const key = quarterAnchor(year, quarter);
    if (!seen.has(key)) {
      seen.add(key);
      firsts.add(release.version);
    }
  }
  return firsts;
}

/** Editorial changelog shell — year rail + release feed (DESIGN_GUIDE §15). */
export function ChangelogView({ releases }: ChangelogViewProps) {
  const groups = buildChangelogNav(releases);
  const quarterFirsts = firstInQuarterKeys(releases);

  if (releases.length === 0) {
    return (
      <div className="changelog-empty">
        No tagged releases yet. Entries appear here when the version release
        pipeline updates CHANGELOG.md.
      </div>
    );
  }

  return (
    <div className="changelog-layout">
      <aside className="changelog-aside">
        <div className="changelog-aside-sticky">
          <ChangelogYearNav groups={groups} />
        </div>
      </aside>
      <div className="changelog-feed">
        {releases.map((release) => (
          <ChangelogEntry
            key={release.version}
            release={release}
            showQuarterMarker={quarterFirsts.has(release.version)}
          />
        ))}
        <ChangelogFooterStrip />
      </div>
    </div>
  );
}
