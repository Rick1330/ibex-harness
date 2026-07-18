import Link from "next/link";
import { ExternalLink } from "lucide-react";

const GITHUB_REPO = "https://github.com/Rick1330/ibex-harness";

export function ChangelogFooterStrip() {
  return (
    <footer className="changelog-footer">
      <p className="changelog-footer-title">Machine-readable history</p>
      <p className="changelog-footer-copy">
        This page is curated for reading. For the full automated record —
        every conventional commit — use the sources below.
      </p>
      <div className="changelog-footer-links">
        <Link
          href={`${GITHUB_REPO}/releases`}
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub Releases
          <ExternalLink className="size-3.5" aria-hidden />
        </Link>
        <Link
          href={`${GITHUB_REPO}/blob/main/CHANGELOG.md`}
          target="_blank"
          rel="noopener noreferrer"
        >
          CHANGELOG.md
          <ExternalLink className="size-3.5" aria-hidden />
        </Link>
        <Link href="/releases/rss.xml">RSS feed</Link>
      </div>
    </footer>
  );
}
