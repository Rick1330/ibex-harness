import Link from "next/link";

import { SectionShell } from "@/components/chrome/section-shell";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

function formatReleaseDate(date: string | null): string {
  if (!date) return "—";
  return date.replaceAll("-", ".");
}

/** §07 · Changelog Peek — latest 3 releases (design §6). */
export function LandingChangelogPeek() {
  const releases = readReleasesFromChangelog().slice(0, 3);

  return (
    <SectionShell
      id="changelog"
      section="§07"
      label="CHANGELOG"
      docHref="/releases"
      docLabel="Full changelog"
    >
      <ul className="divide-y divide-border border-y border-border">
        {releases.map((release) => (
          <li key={release.version} className="py-5">
            <div className="flex flex-wrap items-baseline gap-3">
              <p className="font-mono text-xs text-foreground-muted">
                {formatReleaseDate(release.date)}
              </p>
              <h3 className="font-display text-xl tracking-[-0.02em]">
                {release.version}
              </h3>
            </div>
            {release.summary ? (
              <p className="mt-2 max-w-[62ch] text-sm text-foreground-muted">
                {release.summary}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="mt-6">
        <Link
          href="/releases"
          className="font-mono text-xs text-foreground-muted transition-colors hover:text-accent"
        >
          Full changelog →
        </Link>
      </p>
    </SectionShell>
  );
}
