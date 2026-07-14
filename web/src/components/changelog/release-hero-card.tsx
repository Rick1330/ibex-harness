import Link from "next/link";
import { ExternalLink, GitBranch, Package } from "lucide-react";

import { releaseTypeBadgeClass } from "@/components/changelog/release-type-badge";
import { cn } from "@/lib/cn";
import type { ReleaseEntry } from "@/lib/changelog";
import { countBySectionTitle } from "@/lib/changelog";

const GITHUB_REPO = "https://github.com/Rick1330/ibex-harness";

type ReleaseHeroCardProps = Readonly<{
  release: ReleaseEntry;
}>;

function formatReleaseDate(date: string | null): string | null {
  if (!date) return null;
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

function summaryLine(counts: ReadonlyMap<string, number>): string {
  const parts: string[] = [];
  const features = counts.get("Features");
  const fixes = counts.get("Bug Fixes");
  const performance = counts.get("Performance Improvements");
  const breaking = counts.get("Breaking Changes");
  if (features) parts.push(`${features} features`);
  if (fixes) parts.push(`${fixes} fixes`);
  if (performance) parts.push(`${performance} performance`);
  if (breaking) parts.push(`${breaking} breaking`);
  return parts.join(" · ");
}

export function ReleaseHeroCard({ release }: ReleaseHeroCardProps) {
  const badgeClass = releaseTypeBadgeClass(release.type);
  const counts = countBySectionTitle(release);
  const summary = summaryLine(counts);
  const formattedDate = formatReleaseDate(release.date);
  const tag = `v${release.version}`;
  const releaseUrl = `${GITHUB_REPO}/releases/tag/${tag}`;

  const ctaClass = cn(
    "inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-sm border border-border bg-canvas px-4 py-2 sm:w-auto",
    "text-sm font-medium text-text-primary transition-colors hover:bg-panel-raised",
  );

  return (
    <div className="rounded-md border border-border-strong bg-panel p-4 sm:p-6 md:p-8">
      <div className="mb-4 flex flex-wrap items-center gap-2 sm:gap-3">
        <span className="font-mono text-2xl font-bold tracking-tight text-text-primary sm:text-3xl md:text-4xl">
          {tag}
        </span>
        <span className={badgeClass}>{release.type}</span>
        {formattedDate ? (
          <time className="w-full text-sm text-text-secondary sm:w-auto">
            {formattedDate}
          </time>
        ) : null}
      </div>

      {release.summary ? (
        <p className="mb-4 max-w-2xl text-sm leading-relaxed text-text-secondary sm:text-base">
          {release.summary}
        </p>
      ) : null}

      {summary ? (
        <p className="mb-6 font-mono text-xs text-text-tertiary sm:text-sm">
          {summary}
        </p>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3">
        <Link href={releaseUrl} className={ctaClass} target="_blank" rel="noopener noreferrer">
          <Package className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          GitHub Release
          <ExternalLink className="size-4 shrink-0 text-text-tertiary" aria-hidden />
        </Link>
        <Link
          href={`${GITHUB_REPO}/tags`}
          className={ctaClass}
          target="_blank"
          rel="noopener noreferrer"
        >
          <GitBranch className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          All tags
        </Link>
        <Link
          href={`${releaseUrl}#assets`}
          className={ctaClass}
          target="_blank"
          rel="noopener noreferrer"
        >
          SBOM assets
          <ExternalLink className="size-4 shrink-0 text-text-tertiary" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
