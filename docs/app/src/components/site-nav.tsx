"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { SiteNavActions, SiteNavMobileMenu } from "@/components/site-nav-actions";
import { SiteNavLinks } from "@/components/site-nav-links";

export function SiteNav() {
  const pathname = usePathname();
  const onDocs = pathname.startsWith("/docs");
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header
      data-site-nav
      className="site-nav sticky top-0 z-50 w-full border-b border-border/80 bg-background/90 backdrop-blur-xl supports-[backdrop-filter]:bg-background/80"
    >
      <div className="site-nav-inner flex h-[var(--site-nav-height)] w-full items-stretch gap-0 px-4 sm:px-6 lg:px-8">
        <Link
          href="/docs/getting-started/introduction"
          className="group flex shrink-0 items-center gap-2.5 border-e border-border/70 pe-4 sm:pe-6"
        >
          <div className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-foreground shadow-sm">
            <span className="text-[10px] font-black leading-none text-background">
              I
            </span>
          </div>
          <div className="hidden items-baseline gap-1 sm:flex">
            <span className="text-sm font-semibold tracking-tight text-foreground">
              IBEX
            </span>
            <span className="text-sm font-normal tracking-tight text-muted-foreground">
              Harness
            </span>
          </div>
        </Link>

        <nav
          aria-label="Site sections"
          className="hidden min-w-0 flex-1 items-stretch ps-1 md:flex"
        >
          <SiteNavLinks pathname={pathname} variant="desktop" />
        </nav>

        <SiteNavActions
          onDocs={onDocs}
          mobileOpen={mobileOpen}
          onToggleMobile={() => { setMobileOpen((open) => !open); }}
        />
      </div>

      <SiteNavMobileMenu
        open={mobileOpen}
        pathname={pathname}
        onNavigate={() => { setMobileOpen(false); }}
      />
    </header>
  );
}
