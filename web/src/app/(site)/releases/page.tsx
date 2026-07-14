import type { Metadata } from "next";
import Link from "next/link";

import { ChangelogFooterStrip } from "@/components/changelog/changelog-footer-strip";
import { ReleaseHeroCard } from "@/components/changelog/release-hero-card";
import { ReleaseNotesPanel } from "@/components/changelog/release-notes-panel";
import { ReleaseTimeline } from "@/components/changelog/release-timeline";
import { PageIntro } from "@/components/layout/page-intro";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

export const metadata: Metadata = {
  title: "Changelog",
  description:
    "What shipped in each IBEX Harness release — curated highlights from CHANGELOG.md.",
};

export default function ReleasesPage() {
  const allReleases = readReleasesFromChangelog();
  const [latest, ...older] = allReleases;

  return (
    <main className="container mx-auto max-w-5xl overflow-x-hidden px-4 py-10 sm:py-12 md:px-6 md:py-16 lg:px-8">
      <PageIntro
        section="Changelog"
        title="Release history"
        description="What shipped in each IBEX Harness release. Highlights are curated automatically from the version release pipeline; expand any section for the full list."
      />

      <p className="mb-8 -mt-4 text-sm leading-relaxed text-text-secondary sm:mb-10">
        New versions are proposed weekly (Sundays 08:00 UTC) and published when
        the release PR merges. See{" "}
        <Link
          href="https://github.com/Rick1330/ibex-harness/blob/main/web/engineering/RELEASING.md"
          className="text-text-primary underline-offset-2 hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          RELEASING.md
        </Link>{" "}
        for the full process.
      </p>

      {allReleases.length === 0 ? (
        <div className="rounded-xl border border-border bg-panel p-6 text-sm text-text-secondary">
          No tagged releases yet. Release entries appear here automatically
          when the version release pipeline updates CHANGELOG.md for the first
          published version.
        </div>
      ) : null}

      {latest ? (
        <div className="space-y-8">
          <ReleaseHeroCard release={latest} />
          <ReleaseNotesPanel release={latest} />
        </div>
      ) : null}

      {older.length > 0 ? (
        <div className="mt-12">
          <ReleaseTimeline releases={older} />
        </div>
      ) : null}

      {allReleases.length > 0 ? <ChangelogFooterStrip /> : null}
    </main>
  );
}
