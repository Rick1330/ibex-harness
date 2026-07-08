"use client";

import type { PageTree } from "fumadocs-core/server";
import {
  SidebarFolder,
  SidebarFolderContent,
  SidebarFolderTrigger,
  SidebarItem,
} from "fumadocs-ui/layouts/docs/sidebar";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import {
  baseUrlFromPathname,
  toNavUrl,
} from "@/lib/sidebar-icons";
import { resolveLeafNavIcon } from "@/lib/sidebar-page-icon";
import {
  folderContainsPath,
  resolveFolderSectionSlug,
} from "@/lib/sidebar-folder-slug";
import {
  resolveFolderDefaultOpen,
  resolveFolderHeaderIcon,
} from "@/lib/sidebar-folder-present";
import { PathSyncedSidebarFolder } from "@/components/layout/path-synced-sidebar-folder";
import { cn } from "@/lib/cn";

/** Top-level section folder headers. */
export const docsSectionHeaderClassName = cn(
  "sidebar-nav-section flex w-full min-h-9 items-center gap-2.5 rounded-[4px]",
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-secondary",
  "mb-0.5 mt-4 transition-none first:mt-0",
  "hover:bg-panel-raised hover:text-text-primary",
  "[&_[data-icon]]:ms-auto [&_[data-icon]]:size-4 [&_[data-icon]]:text-text-primary",
  "[&_.sidebar-section-icon]:text-text-primary",
);

/** Nested folder headers (milestones, sub-sections). */
export const docsNestedFolderHeaderClassName = cn(
  "sidebar-nav-section sidebar-nav-section--nested flex w-full min-h-8 items-center gap-2 rounded-[4px]",
  "px-2.5 py-1.5 text-[0.8125rem] font-semibold normal-case tracking-normal text-text-secondary",
  "mb-0.5 transition-none",
  "hover:bg-panel-raised hover:text-text-primary",
  "[&_[data-icon]]:ms-auto [&_[data-icon]]:size-3.5",
);

/** Leaf page links — icon + label, matches footer prev/next. */
const leafItemClassName = cn(
  "sidebar-nav-item flex min-h-9 items-center gap-2.5 rounded-[4px]",
  "border-s-2 border-transparent py-2 pe-3 ps-[10px] text-[0.875rem] leading-5 text-text-secondary",
  "transition-none hover:bg-panel-raised hover:text-text-primary",
  "data-[active=true]:border-accent data-[active=true]:bg-panel-raised",
  "data-[active=true]:font-medium data-[active=true]:text-text-primary",
  "[&_svg:not([data-icon])]:size-4 [&_svg:not([data-icon])]:shrink-0",
);

export function DocsSidebarItem({ item }: { item: PageTree.Item }) {
  const pathname = usePathname();
  const baseUrl = baseUrlFromPathname(toNavUrl(pathname));
  const isMilestone = item.url.includes("/milestones/");

  return (
    <SidebarItem
      className={cn(leafItemClassName, isMilestone && "sidebar-nav-item--milestone")}
      external={item.external}
      href={item.url}
      icon={resolveLeafNavIcon(item.url, baseUrl)}
    >
      <span className="sidebar-nav-item-label min-w-0 flex-1">{item.name}</span>
    </SidebarItem>
  );
}

export function DocsSidebarFolder({
  item,
  level,
  children,
}: {
  item: PageTree.Folder;
  level: number;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const baseUrl = baseUrlFromPathname(toNavUrl(pathname));
  const sectionSlug = resolveFolderSectionSlug(item, baseUrl);
  const defaultOpen = resolveFolderDefaultOpen(item, level, pathname);
  const sectionIcon = resolveFolderHeaderIcon(item, level, baseUrl, sectionSlug);
  const headerClass =
    level <= 1 ? docsSectionHeaderClassName : docsNestedFolderHeaderClassName;

  if (level <= 1) {
    return (
      <PathSyncedSidebarFolder
        containsPath={folderContainsPath(item, pathname)}
        headerClassName={headerClass}
        header={
          <>
            {sectionIcon}
            <span className="min-w-0 flex-1 text-left break-words">{item.name}</span>
          </>
        }
        depth={level}
      >
        {children}
      </PathSyncedSidebarFolder>
    );
  }

  const folderKey =
    item.index === undefined ? sectionSlug : item.index.url;

  return (
    <SidebarFolder
      key={`${folderKey}-${level}`}
      defaultOpen={defaultOpen}
    >
      <SidebarFolderTrigger className={headerClass}>
        {sectionIcon}
        <span className="min-w-0 flex-1 text-left break-words">{item.name}</span>
      </SidebarFolderTrigger>
      <SidebarFolderContent
        className="sidebar-folder-children"
        data-sidebar-depth={level}
      >
        {children}
      </SidebarFolderContent>
    </SidebarFolder>
  );
}

export function docsSidebarItemClassName(extra?: string) {
  return cn(leafItemClassName, extra);
}
