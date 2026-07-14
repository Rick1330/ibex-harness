import Link from "next/link";
import { ExternalLink } from "lucide-react";

const GITHUB_REPO = "https://github.com/Rick1330/ibex-harness";

export function ChangelogFooterStrip() {
  return (
    <div className="mt-12 rounded-md border border-border bg-panel p-5 text-sm text-text-secondary">
      <p className="mb-3 font-medium text-text-primary">
        Complete machine-readable history
      </p>
      <p className="mb-4 leading-relaxed">
        The public changelog shows curated highlights from each release. For the
        full automated record — including every conventional commit — use the
        links below.
      </p>
      <div className="flex flex-wrap gap-4">
        <Link
          href={`${GITHUB_REPO}/releases`}
          className="inline-flex items-center gap-1.5 text-text-primary hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub Releases
          <ExternalLink className="size-3.5 text-text-tertiary" aria-hidden />
        </Link>
        <Link
          href={`${GITHUB_REPO}/blob/main/CHANGELOG.md`}
          className="inline-flex items-center gap-1.5 text-text-primary hover:underline"
          target="_blank"
          rel="noopener noreferrer"
        >
          CHANGELOG.md
          <ExternalLink className="size-3.5 text-text-tertiary" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
