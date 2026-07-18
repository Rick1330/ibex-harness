import Link from "next/link";

import {
  FOOTER_LINKS,
  REPO_URL,
  STATUS_STUB,
} from "@/lib/landing-content";

const COPYRIGHT_YEAR = 2026;

function FooterLinkColumn({
  title,
  links,
}: Readonly<{
  title: string;
  links: ReadonlyArray<{ label: string; href: string; external?: boolean }>;
}>) {
  return (
    <div className="landing-footer-col">
      <p className="landing-footer-col-label">{title}</p>
      <nav aria-label={title} className="landing-footer-col-nav">
        {links.map((link) =>
          link.external ? (
            <a
              key={`${link.href}-${link.label}`}
              href={link.href}
              rel="noopener noreferrer"
              target="_blank"
              className="landing-footer-link"
            >
              {link.label}
            </a>
          ) : (
            <Link
              key={link.href}
              href={link.href}
              className="landing-footer-link"
            >
              {link.label}
            </Link>
          ),
        )}
      </nav>
    </div>
  );
}

/**
 * Footer — brand + 3 link columns + copyright strip
 * (screenshot / DESIGN_GUIDE.md §12.8).
 */
export function LandingFooter() {
  return (
    <footer className="landing-footer border-t border-border">
      <div className="landing-inner landing-footer-inner">
        <div className="landing-footer-grid">
          <div className="landing-footer-brand">
            <Link href="/" className="landing-footer-wordmark">
              Ibex Harness
            </Link>
            <p className="landing-footer-blurb">
              An open-source control plane for production AI agents. Built by
              engineers, for engineers.
            </p>
            <p className="landing-footer-status">
              <span className="landing-footer-status-dot" aria-hidden />
              {STATUS_STUB}
            </p>
          </div>
          <FooterLinkColumn title="PRODUCT" links={FOOTER_LINKS.product} />
          <FooterLinkColumn title="COMMUNITY" links={FOOTER_LINKS.community} />
          <FooterLinkColumn title="LEGAL" links={FOOTER_LINKS.legal} />
        </div>

        <div className="landing-footer-bar">
          <span className="landing-footer-copy">
            © {COPYRIGHT_YEAR} IBEX HARNESS — MIT
          </span>
          <a
            href={REPO_URL}
            className="landing-footer-tagline"
            rel="noopener noreferrer"
            target="_blank"
          >
            Built for the agentic age.
          </a>
        </div>
      </div>
    </footer>
  );
}
