import Link from "next/link";
import { ExternalLink, GitBranch, Package } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ReleaseEntry } from "@/lib/changelog";
import { countBySectionTitle } from "@/lib/changelog";

const GITHUB_REPO = "https://github.com/Rick1330/ibex-harness";

const versionBadge = {
  major:
    "rounded-full bg-text-primary px-2.5 py-0.5 font-mono text-xs font-bold text-canvas",
  minor:
    "rounded-full border border-border bg-panel px-2.5 py-0.5 font-mono text-xs font-bold text-text-primary",
  patch:
    "rounded-full border border-border bg-panel-raised px-2.5 py-0.5 font-mono text-xs font-bold text-text-secondary",
} as const;

type ReleaseHeroCardProps = Readonly<{
  release: ReleaseEntry;
}>;

function formatReleaseDate(date: string | null): string | null {
  if (!date) return null;
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function summaryLine(counts: Record<string, number>): string {
  const parts: string[] = [];
  if (counts.Features) parts.push(`${counts.Features} features`);
  if (counts["Bug Fixes"]) parts.push(`${counts["Bug Fixes"]} fixes`);
  if (counts["Performance Improvements"]) {
    parts.push(`${counts["Performance Improvements"]} performance`);
  }
  if (counts["Breaking Changes"]) {
    parts.push(`${counts["Breaking Changes"]} breaking`);
  }
  return parts.join(" · ");
}

export function ReleaseHeroCard({ release }: ReleaseHeroCardProps) {
  const badgeClass = versionBadge[release.type] ?? versionBadge.minor;
  const counts = countBySectionTitle(release);
  const summary = summaryLine(counts);
  const formattedDate = formatReleaseDate(release.date);
  const tag = `v${release.version}`;
  const releaseUrl = `${GITHUB_REPO}/releases/tag/${tag}`;

  const ctaClass = cn(
    "inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-md border border-border bg-canvas px-4 py-2 sm:w-auto",
    "text-sm font-medium text-text-primary transition-colors hover:bg-panel-raised",
  );

  return (
    <div className="rounded-xl border border-border-strong bg-panel p-4 sm:p-6 md:p-8">
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
          <Package className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
          GitHub Release
          <ExternalLink className="size-3.5 shrink-0 text-text-tertiary" aria-hidden />
        </Link>
        <Link
          href={`${GITHUB_REPO}/tags`}
          className={ctaClass}
          target="_blank"
          rel="noopener noreferrer"
        >
          <GitBranch className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
          All tags
        </Link>
        <Link
          href={`${releaseUrl}#assets`}
          className={ctaClass}
          target="_blank"
          rel="noopener noreferrer"
        >
          SBOM assets
          <ExternalLink className="size-3.5 shrink-0 text-text-tertiary" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
