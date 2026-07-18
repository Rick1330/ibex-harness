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
        <a
          href={`${GITHUB_REPO}/releases`}
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub Releases
          <ExternalLink className="size-4" strokeWidth={1.5} aria-hidden />
        </a>
        <a
          href={`${GITHUB_REPO}/blob/main/CHANGELOG.md`}
          target="_blank"
          rel="noopener noreferrer"
        >
          CHANGELOG.md
          <ExternalLink className="size-4" strokeWidth={1.5} aria-hidden />
        </a>
        <a href="/releases/rss.xml">RSS feed</a>
      </div>
    </footer>
  );
}
