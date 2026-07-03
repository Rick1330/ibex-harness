"use client";

import type { ReactNode } from "react";
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

function shouldSkipHubLink(section: MobileNavSectionConfig): boolean {
  return section.dataKey === "benchmarkPages";
}

function renderHubLink(
  section: MobileNavSectionConfig,
  pathname: string,
  onClose: () => void,
): ReactNode {
  if (!section.hub || shouldSkipHubLink(section)) {
    return null;
  }

  return (
    <HubLink
      href={section.hub.href}
      label={section.hub.label}
      pathname={pathname}
      onNavigate={onClose}
    />
  );
}

type MobileDrawerTreeSectionProps = Readonly<{
  section: MobileNavSectionConfig;
  data: MobileNavData;
  hub: ReactNode;
  onClose: () => void;
}>;

function MobileDrawerTreeSection({
  section,
  data,
  hub,
  onClose,
}: MobileDrawerTreeSectionProps) {
  if (!section.baseUrl) {
    return null;
  }

  const treeKey = section.dataKey === "docsTree" ? "docsTree" : "roadmapTree";
  const nodes = getSectionTree(data, treeKey);

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

type ListPageDataKey = "blogPosts" | "releasePages" | "benchmarkPages";

function listPageDataKey(section: MobileNavSectionConfig): ListPageDataKey {
  if (section.dataKey === "blogPosts") {
    return "blogPosts";
  }
  if (section.dataKey === "benchmarkPages") {
    return "benchmarkPages";
  }
  return "releasePages";
}

type MobileDrawerListSectionProps = Readonly<{
  section: MobileNavSectionConfig;
  data: MobileNavData;
  hub: ReactNode;
  pathname: string;
  onClose: () => void;
}>;

function MobileDrawerListSection({
  section,
  data,
  hub,
  pathname,
  onClose,
}: MobileDrawerListSectionProps) {
  const skipHub = shouldSkipHubLink(section);
  const pageDataKey = listPageDataKey(section);
  const pages = getSectionPages(data, pageDataKey).filter((page) => {
    if (skipHub) {
      return true;
    }
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
  const hub = renderHubLink(section, pathname, onClose);

  if (section.kind === "tree") {
    return (
      <MobileDrawerTreeSection
        section={section}
        data={data}
        hub={hub}
        onClose={onClose}
      />
    );
  }

  return (
    <MobileDrawerListSection
      section={section}
      data={data}
      hub={hub}
      pathname={pathname}
      onClose={onClose}
    />
  );
}
