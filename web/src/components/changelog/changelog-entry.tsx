import Link from "next/link";

import {
  editorialSectionLabel,
  formatChangelogDate,
  isNewRelease,
  quarterAnchor,
  releaseQuarter,
  releaseYear,
} from "@/lib/changelog/grouping";
import type { ReleaseEntry, ReleaseSection } from "@/lib/changelog/types";
import { cn } from "@/lib/cn";

const GITHUB_REPO = "https://github.com/Rick1330/ibex-harness";

type ChangelogEntryProps = Readonly<{
  release: ReleaseEntry;
  /** Render quarter marker when this is the first release in that quarter. */
  showQuarterMarker?: boolean;
}>;

type SectionItem = ReleaseSection["items"][number];

function typeClass(type: ReleaseEntry["type"]): string {
  if (type === "major") return "changelog-type changelog-type-major";
  if (type === "minor") return "changelog-type changelog-type-minor";
  return "changelog-type changelog-type-patch";
}

function ItemRow({ item }: Readonly<{ item: SectionItem }>) {
  return (
    <li
      className={cn(
        "changelog-item",
        item.priority === "highlight" && "changelog-item-highlight",
      )}
    >
      {item.scope ? (
        <span className="changelog-item-scope">{item.scope}</span>
      ) : null}
      <span className="changelog-item-text">{item.description}</span>
      {item.issueUrl && item.issueNumber ? (
        <Link
          href={item.issueUrl}
          className="changelog-item-issue"
          target="_blank"
          rel="noopener noreferrer"
        >
          #{item.issueNumber}
        </Link>
      ) : null}
    </li>
  );
}

function SectionBlock({
  version,
  section,
}: Readonly<{ version: string; section: ReleaseSection }>) {
  if (section.items.length === 0) return null;
  const label = editorialSectionLabel(section.title);
  return (
    <section
      key={`${version}-${section.title}`}
      className="changelog-section"
    >
      <h3 className="changelog-section-label">{label}</h3>
      <ul className="changelog-section-list">
        {section.items.map((item) => (
          <ItemRow
            key={`${section.title}-${item.scope ?? ""}-${item.description}-${item.issueNumber ?? item.commitSha ?? ""}`}
            item={item}
          />
        ))}
      </ul>
    </section>
  );
}

function EntryHeader({
  release,
  versionAnchor,
  tag,
  fresh,
}: Readonly<{
  release: ReleaseEntry;
  versionAnchor: string;
  tag: string;
  fresh: boolean;
}>) {
  return (
    <header className="changelog-entry-header">
      <p className="changelog-entry-meta">
        <time dateTime={release.date ?? undefined}>
          {formatChangelogDate(release.date)}
        </time>
        <span aria-hidden>·</span>
        <a href={`#${versionAnchor}`} className="changelog-entry-version">
          {tag}
        </a>
        <span aria-hidden>·</span>
        <span className={typeClass(release.type)}>{release.type}</span>
        {fresh ? <span className="changelog-new-pill">New</span> : null}
      </p>

      <h2 id={`${versionAnchor}-title`} className="changelog-entry-title">
        {release.summary?.trim() || `${tag} release notes`}
      </h2>

      <p className="changelog-entry-links">
        <Link
          href={`${GITHUB_REPO}/releases/tag/${tag}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub release
        </Link>
      </p>
    </header>
  );
}

/** Single release block — date · version · type, then mono section lists. */
export function ChangelogEntry({
  release,
  showQuarterMarker = false,
}: ChangelogEntryProps) {
  const year = releaseYear(release.date);
  const quarter = releaseQuarter(release.date);
  const markerId =
    showQuarterMarker && year !== null && quarter !== null
      ? quarterAnchor(year, quarter)
      : undefined;
  const versionAnchor = `v${release.version}`;
  const tag = `v${release.version}`;

  return (
    <article
      className="changelog-entry"
      id={versionAnchor}
      aria-labelledby={`${versionAnchor}-title`}
    >
      {markerId ? (
        <div id={markerId} className="changelog-quarter-marker">
          {year} Q{quarter}
        </div>
      ) : null}

      <EntryHeader
        release={release}
        versionAnchor={versionAnchor}
        tag={tag}
        fresh={isNewRelease(release.date)}
      />

      <div className="changelog-entry-body">
        {release.sections.map((section) => (
          <SectionBlock
            key={`${release.version}-${section.title}`}
            version={release.version}
            section={section}
          />
        ))}
      </div>
    </article>
  );
}
