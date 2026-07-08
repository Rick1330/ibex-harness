import Link from "next/link";

import { BrandLockup } from "@/components/brand-lockup";
import { FOOTER_LINKS } from "@/lib/landing-content";

function FooterLinkColumn({
  title,
  links,
}: Readonly<{
  title: string;
  links: ReadonlyArray<{ label: string; href: string; external?: boolean }>;
}>) {
  return (
    <div>
      <p className="mb-3 text-[11px] font-bold tracking-widest text-muted-foreground">
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
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              {link.label}
            </a>
          ) : (
            <Link
              key={link.href}
              href={link.href}
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
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
      <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-1">
            <BrandLockup showWordmark="always" />
            <p className="mt-3 max-w-xs text-xs leading-relaxed text-muted-foreground">
              Open-source control plane for AI agents — proxy ingress, tenant
              auth, and a memory-ready request path on ibexharness.com.
            </p>
          </div>
          <FooterLinkColumn title="PRODUCT" links={FOOTER_LINKS.product} />
          <FooterLinkColumn title="PROJECT" links={FOOTER_LINKS.project} />
        </div>
        <p className="mt-8 text-xs text-muted-foreground">
          {"© "}
          {year}
          {" IBEX Harness · MIT"}
        </p>
      </div>
    </footer>
  );
}
