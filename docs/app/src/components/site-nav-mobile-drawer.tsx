"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { MobilePageTreeNav } from "@/components/layout/mobile-page-tree-nav";
import { MobileSectionSwitcher } from "@/components/layout/mobile-section-switcher";
import { NavSearch } from "@/components/layout/nav-search";
import { docsSidebarItemClassName } from "@/components/layout/docs-sidebar";
import { cn } from "@/lib/cn";
import type { MobileNavData } from "@/lib/mobile-nav-data";
import {
  getSectionPages,
  getSectionTree,
} from "@/lib/mobile-nav-section-data";
import { navUrlsMatch } from "@/lib/sidebar-nav-pages";
import {
  getActiveMobileSection,
  MOBILE_NAV_SECTIONS,
  resolveActiveMobileSection,
  type MobileNavSectionConfig,
} from "@/lib/site-nav-config";

type SiteNavMobileDrawerProps = Readonly<{
  open: boolean;
  onClose: () => void;
  mobileNavData: MobileNavData;
}>;

function HubLink({
  href,
  label,
  pathname,
  onNavigate,
}: Readonly<{
  href: string;
  label: string;
  pathname: string;
  onNavigate: () => void;
}>) {
  const isActive = navUrlsMatch(href, pathname);

  return (
    <Link
      href={href}
      prefetch
      onClick={onNavigate}
      data-active={isActive ? "true" : undefined}
      className={docsSidebarItemClassName()}
    >
      <span className="min-w-0 flex-1 break-words">{label}</span>
    </Link>
  );
}

function renderSectionContent(
  section: MobileNavSectionConfig,
  data: MobileNavData,
  pathname: string,
  onClose: () => void,
) {
  if (section.kind === "tree") {
    if (!section.baseUrl) return null;

    const nodes = getSectionTree(
      data,
      section.dataKey === "docsTree" ? "docsTree" : "roadmapTree",
    );

    return (
      <>
        {section.hub ? (
          <HubLink
            href={section.hub.href}
            label={section.hub.label}
            pathname={pathname}
            onNavigate={onClose}
          />
        ) : null}
        <MobilePageTreeNav
          nodes={nodes}
          baseUrl={section.baseUrl}
          onNavigate={onClose}
        />
      </>
    );
  }

  const pages = getSectionPages(
    data,
    section.dataKey === "blogPosts" ? "blogPosts" : "releasePages",
  );

  return (
    <>
      {section.hub ? (
        <HubLink
          href={section.hub.href}
          label={section.hub.label}
          pathname={pathname}
          onNavigate={onClose}
        />
      ) : null}
      {pages.map((page) => (
        <Link
          key={page.url}
          href={page.url}
          prefetch
          onClick={onClose}
          data-active={navUrlsMatch(page.url, pathname) ? "true" : undefined}
          className={docsSidebarItemClassName()}
        >
          <span className="min-w-0 flex-1 break-words text-sm">{page.title}</span>
        </Link>
      ))}
    </>
  );
}

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

  useEffect(() => {
    if (!open) return;

    const drawer = document.getElementById("site-nav-mobile-drawer");
    if (!drawer) return;

    const selector =
      'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])';
    const focusable = Array.from(
      drawer.querySelectorAll<HTMLElement>(selector),
    ).filter((el) => !el.hasAttribute("aria-hidden"));

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || focusable.length === 0) return;

      if (event.shiftKey) {
        if (document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        }
        return;
      }

      if (document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    first?.focus();

    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

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
      <nav
        id="site-nav-mobile-drawer"
        aria-label="Mobile navigation"
        aria-modal={open ? true : undefined}
        role="dialog"
        aria-hidden={!open}
        className={cn(
          "fixed left-0 top-[var(--site-nav-height)] z-50 flex md:hidden",
          "h-[calc(100dvh-var(--site-nav-height))] w-full max-w-[20rem] flex-col",
          "border-e border-border bg-canvas transition-transform",
          !open && "pointer-events-none invisible -translate-x-full",
        )}
      >
        <div className="shrink-0 space-y-3 border-b border-border/70 p-3">
          <NavSearch variant="full" className="w-full" />
          <MobileSectionSwitcher
            sections={MOBILE_NAV_SECTIONS}
            activeSectionId={resolveActiveMobileSection(pathname)}
            onSelect={onClose}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {renderSectionContent(
            activeSection,
            mobileNavData,
            pathname,
            onClose,
          )}
        </div>
      </nav>
    </>,
    document.body,
  );
}
