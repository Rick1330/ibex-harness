"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { BrandLockup } from "@/components/brand-lockup";
import type { MobileNavData } from "@/lib/mobile-nav-data";
import { SiteNavActions } from "@/components/site-nav-actions";
import { SiteNavMobileDrawer } from "@/components/site-nav-mobile-drawer";
import { SiteNavLinks } from "@/components/site-nav-links";

type SiteNavProps = Readonly<{
  mobileNavData: MobileNavData;
}>;

export function SiteNav({ mobileNavData }: SiteNavProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileOpen]);

  return (
    <>
      <header
        data-site-nav
        className="site-nav sticky top-0 z-50 w-full border-b border-border/80 bg-background"
      >
        <div className="site-nav-inner h-[var(--site-nav-height)] w-full">
          <div className="site-nav-brand">
            <BrandLockup showWordmark="md" />
          </div>

          <nav
            aria-label="Site sections"
            className="site-nav-links hidden md:flex"
          >
            <SiteNavLinks pathname={pathname} variant="desktop" />
          </nav>

          <SiteNavActions
            mobileOpen={mobileOpen}
            onToggleMobile={() => { setMobileOpen((open) => !open); }}
          />
        </div>
      </header>

      <SiteNavMobileDrawer
        open={mobileOpen}
        onClose={() => { setMobileOpen(false); }}
        mobileNavData={mobileNavData}
      />
    </>
  );
}
