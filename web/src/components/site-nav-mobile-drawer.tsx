"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { MobileDrawerSectionContent } from "@/components/mobile-drawer-section";
import { MobileSectionSwitcher } from "@/components/layout/mobile-section-switcher";
import { NavSearch } from "@/components/layout/nav-search";
import { useMobileDrawerFocusTrap } from "@/components/use-mobile-drawer-focus-trap";
import { cn } from "@/lib/cn";
import type { MobileNavData } from "@/lib/mobile-nav-data";
import {
  getActiveMobileSection,
  LANDING_NAV_LINK,
  MOBILE_NAV_SECTIONS,
  resolveActiveMobileSection,
} from "@/lib/site-nav-config";

const DRAWER_ID = "site-nav-mobile-drawer";

type SiteNavMobileDrawerProps = Readonly<{
  open: boolean;
  onClose: () => void;
  mobileNavData: MobileNavData;
}>;

export function SiteNavMobileDrawer({
  open,
  onClose,
  mobileNavData,
}: SiteNavMobileDrawerProps) {
  const pathname = usePathname();
  const [portalReady, setPortalReady] = useState(false);
  const activeSection = getActiveMobileSection(pathname);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useMobileDrawerFocusTrap(open, DRAWER_ID);

  if (!portalReady) return null;

  return createPortal(
    <>
      <button
        type="button"
        aria-label="Close menu"
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        className={cn(
          "fixed inset-0 top-[var(--site-nav-height)] z-[49] bg-black/50 md:hidden",
          "transition-opacity",
          !open && "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <dialog
        id={DRAWER_ID}
        open={open}
        aria-label="Mobile navigation"
        className={cn(
          "fixed left-0 top-[var(--site-nav-height)] z-50 m-0 flex max-h-none w-full max-w-[20rem] border-0 p-0 md:hidden",
          "h-[calc(100dvh-var(--site-nav-height))] flex-col",
          "border-e border-border bg-canvas transition-transform",
          !open && "pointer-events-none invisible -translate-x-full",
        )}
      >
        <nav aria-label="Mobile section links" className="flex min-h-0 flex-1 flex-col">
        <div className="shrink-0 space-y-3 border-b border-border/70 p-3">
          <Link
            href={LANDING_NAV_LINK.href}
            onClick={onClose}
            className="inline-flex rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
          >
            {LANDING_NAV_LINK.text}
          </Link>
          <NavSearch variant="full" className="w-full" />
          <MobileSectionSwitcher
            sections={MOBILE_NAV_SECTIONS}
            activeSectionId={resolveActiveMobileSection(pathname)}
            onSelect={onClose}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          <MobileDrawerSectionContent
            section={activeSection}
            data={mobileNavData}
            pathname={pathname}
            onClose={onClose}
          />
        </div>
        </nav>
      </dialog>
    </>,
    document.body,
  );
}
