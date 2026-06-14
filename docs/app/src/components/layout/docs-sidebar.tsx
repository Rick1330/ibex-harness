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
  folderSectionSlugFromUrl,
  getSectionIconForSlug,
  navIconElement,
  roadmapNavIconElement,
  SidebarIcon,
} from "@/lib/sidebar-icons";
import { cn } from "@/lib/cn";

function folderSectionSlug(
  item: PageTree.Folder,
  baseUrl: "/docs" | "/roadmap",
): string {
  const prefix =
    baseUrl === "/docs" ? /^\/docs\/?/ : /^\/roadmap\/?/;

  for (const child of item.children) {
    if (child.type === "page") {
      const section = child.url.replace(prefix, "").split("/")[0];
      if (section) return section;
    }
    if (child.type === "folder") {
      const nested = folderSectionSlug(child, baseUrl);
      if (nested !== "section") return nested;
    }
  }
  return "section";
}

/** Top-level section folder headers. */
const sectionHeaderClassName = cn(
  "sidebar-nav-section flex w-full min-h-9 items-center gap-2.5 rounded-[4px]",
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-secondary",
  "mb-0.5 mt-4 transition-none first:mt-0",
  "hover:bg-panel-raised hover:text-text-primary",
  "[&_[data-icon]]:ms-auto [&_[data-icon]]:size-4 [&_[data-icon]]:text-text-primary",
  "[&_.sidebar-section-icon]:text-text-primary",
);

/** Nested folder headers (milestones, sub-sections). */
const nestedFolderHeaderClassName = cn(
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

function folderContainsPath(
  folder: PageTree.Folder,
  pathname: string,
): boolean {
  if (folder.index?.url === pathname) return true;

  return folder.children.some((child) => {
    if (child.type === "page") return child.url === pathname;
    if (child.type === "folder") return folderContainsPath(child, pathname);
    return false;
  });
}

export function DocsSidebarItem({ item }: { item: PageTree.Item }) {
  const pathname = usePathname();
  const baseUrl = baseUrlFromPathname(pathname);
  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;
  const isMilestone = item.url.includes("/milestones/");

  return (
    <SidebarItem
      className={cn(leafItemClassName, isMilestone && "sidebar-nav-item--milestone")}
      external={item.external}
      href={item.url}
      icon={item.icon ?? iconResolver(undefined, item.url)}
    >
      {item.name}
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
  const baseUrl = baseUrlFromPathname(pathname);
  const containsPath = folderContainsPath(item, pathname);
  const defaultOpen =
    containsPath || (level > 1 && (item.defaultOpen ?? false));

  const sectionSlug =
    item.index?.url != null
      ? folderSectionSlugFromUrl(item.index.url)
      : folderSectionSlug(item, baseUrl);

  const sectionIcon =
    level <= 1 ? (
      <SidebarIcon
        className="sidebar-section-icon"
        icon={getSectionIconForSlug(sectionSlug, baseUrl)}
      />
    ) : (
      item.icon
    );

  const headerClass =
    level <= 1 ? sectionHeaderClassName : nestedFolderHeaderClassName;

  return (
    <SidebarFolder
      key={level <= 1 ? `${sectionSlug}-${pathname}` : sectionSlug}
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
