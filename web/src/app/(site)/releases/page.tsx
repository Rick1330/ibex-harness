import type { Metadata } from "next";
import Link from "next/link";

import { ChangelogView } from "@/components/changelog/changelog-view";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

export const metadata: Metadata = {
  title: "Changelog",
  description:
    "What shipped in each IBEX Harness release — curated from CHANGELOG.md.",
  alternates: {
    types: {
      "application/rss+xml": "/releases/rss.xml",
    },
  },
};

/** Refresh daily so "New" badges stay accurate without redeploy. */
export const revalidate = 86_400;

export default function ReleasesPage() {
  const releases = readReleasesFromChangelog();

  return (
    <main className="changelog-page">
      <header className="changelog-intro">
        <h1 className="changelog-title">Changelog</h1>
        <p className="changelog-lede">
          What shipped in each IBEX Harness release — features, fixes, and
          breaking changes, grouped by year.
        </p>
        <p className="changelog-process">
          New versions are proposed weekly (Sundays 08:00 UTC) and published when
          the release PR merges. See{" "}
          <Link
            href="https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/RELEASING.md"
            target="_blank"
            rel="noopener noreferrer"
          >
            RELEASING.md
          </Link>{" "}
          for the process.
        </p>
      </header>

      <ChangelogView releases={releases} />
    </main>
  );
}
