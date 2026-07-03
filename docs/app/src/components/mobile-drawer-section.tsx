"use client";

import Link from "next/link";

import { MobilePageTreeNav } from "@/components/layout/mobile-page-tree-nav";
import { docsSidebarItemClassName } from "@/components/layout/docs-sidebar";
import type { MobileNavData } from "@/lib/mobile-nav-data";
import {
  getSectionPages,
  getSectionTree,
} from "@/lib/mobile-nav-section-data";
import { navUrlsMatch } from "@/lib/sidebar-nav-pages";
import type { MobileNavSectionConfig } from "@/lib/site-nav-config";

type HubLinkProps = Readonly<{
  href: string;
  label: string;
  pathname: string;
  onNavigate: () => void;
}>;

function HubLink({ href, label, pathname, onNavigate }: HubLinkProps) {
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

type MobileDrawerSectionContentProps = Readonly<{
  section: MobileNavSectionConfig;
  data: MobileNavData;
  pathname: string;
  onClose: () => void;
}>;

export function MobileDrawerSectionContent({
  section,
  data,
  pathname,
  onClose,
}: MobileDrawerSectionContentProps) {
  const hub = section.hub ? (
    <HubLink
      href={section.hub.href}
      label={section.hub.label}
      pathname={pathname}
      onNavigate={onClose}
    />
  ) : null;

  if (section.kind === "tree") {
    if (!section.baseUrl) return null;

    const nodes = getSectionTree(
      data,
      section.dataKey === "docsTree" ? "docsTree" : "roadmapTree",
    );

    return (
      <>
        {hub}
        <MobilePageTreeNav
          nodes={nodes}
          baseUrl={section.baseUrl}
          onNavigate={onClose}
        />
      </>
    );
  }

  let pageDataKey: "blogPosts" | "releasePages" | "benchmarkPages" = "releasePages";
  if (section.dataKey === "blogPosts") {
    pageDataKey = "blogPosts";
  } else if (section.dataKey === "benchmarkPages") {
    pageDataKey = "benchmarkPages";
  }

  const pages = getSectionPages(data, pageDataKey).filter((page) => {
    return page.url !== section.hub?.href;
  });

  return (
    <>
      {hub}
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
