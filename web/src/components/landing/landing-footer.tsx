import Link from "next/link";

import { BrandLockup } from "@/components/brand-lockup";
import {
  FOOTER_LINKS,
  REPO_URL,
  SITE_VERSION,
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
              key={link.href}
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
    <footer className="border-t border-border">
      <div className="mx-auto max-w-[var(--container)] px-5 py-12 sm:px-8">
        <p className="mb-8 font-mono text-xs uppercase tracking-[0.14em] text-foreground-muted">
          §09 · FOOTER
        </p>
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-1">
            <BrandLockup showWordmark="always" />
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-foreground-muted">
              Open-source control plane for AI agents — proxy ingress, tenant
              auth, and a memory-ready request path.
            </p>
          </div>
          <FooterLinkColumn title="Product" links={FOOTER_LINKS.product} />
          <FooterLinkColumn title="Community" links={FOOTER_LINKS.community} />
          <FooterLinkColumn title="Project" links={FOOTER_LINKS.project} />
        </div>
        <div className="mt-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-6 font-mono text-xs text-foreground-muted">
          <span>
            © {year} IBEX Harness · MIT
          </span>
          <span>{SITE_VERSION}</span>
          <span className="inline-flex items-center gap-2">
            <span
              className="size-1.5 rounded-full bg-success"
              aria-hidden
            />
            {STATUS_STUB}
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
