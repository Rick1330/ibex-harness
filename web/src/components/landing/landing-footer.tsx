import Link from "next/link";

import {
  FOOTER_LINKS,
  REPO_URL,
  STATUS_STUB,
} from "@/lib/landing-content";

function FooterLinkColumn({
  title,
  links,
}: Readonly<{
  title: string;
  links: ReadonlyArray<{ label: string; href: string; external?: boolean }>;
}>) {
  return (
    <div>
      <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.12em] text-foreground-muted">
        {title}
      </p>
      <nav aria-label={title} className="flex flex-col gap-2">
        {links.map((link) =>
          link.external ? (
            <a
              key={`${link.href}-${link.label}`}
              href={link.href}
              rel="noopener noreferrer"
              target="_blank"
              className="text-sm text-foreground-muted transition-colors hover:text-foreground"
            >
              {link.label}
            </a>
          ) : (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-foreground-muted transition-colors hover:text-foreground"
            >
              {link.label}
            </Link>
          ),
        )}
      </nav>
    </div>
  );
}

export function LandingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border bg-surface-1">
      <div className="landing-inner py-12 sm:py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="font-display text-xl italic tracking-[-0.02em]">
              Ibex Harness
            </p>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-foreground-muted">
              An open-source control plane for production AI agents. Built by
              engineers, for engineers.
            </p>
            <p className="mt-4 inline-flex items-center gap-2 font-mono text-xs text-foreground-muted">
              <span className="size-1.5 rounded-full bg-success" aria-hidden />
              {STATUS_STUB}
            </p>
          </div>
          <FooterLinkColumn title="Product" links={FOOTER_LINKS.product} />
          <FooterLinkColumn title="Community" links={FOOTER_LINKS.community} />
          <FooterLinkColumn title="Legal" links={FOOTER_LINKS.legal} />
        </div>
        <div className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6 font-mono text-xs text-foreground-muted">
          <span>
            © {year} IBEX HARNESS · MIT
          </span>
          <a
            href={REPO_URL}
            className="transition-colors hover:text-foreground"
            rel="noopener noreferrer"
            target="_blank"
          >
            GitHub ↗
          </a>
        </div>
      </div>
    </footer>
  );
}
