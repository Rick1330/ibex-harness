import type { PageTree } from "fumadocs-core/server";
import type { ReactNode } from "react";

import {
  baseUrlFromPathname,
  folderSectionSlugFromUrl,
  getSectionIconForSlug,
  type ContentBaseUrl,
} from "@/lib/sidebar-icon-resolvers";
import {
  navIconElement,
  roadmapNavIconElement,
  SidebarIcon,
  toNavUrl,
  toSectionSlug,
} from "@/lib/sidebar-icons";

function folderSectionSlug(
  item: PageTree.Folder,
  baseUrl: ContentBaseUrl,
): string {
  const prefix = baseUrl === "/docs" ? "/docs/" : "/roadmap/";

  for (const child of item.children) {
    if (child.type === "page") {
      const withoutPrefix = child.url.startsWith(prefix)
        ? child.url.slice(prefix.length)
        : child.url;
      const section = withoutPrefix.split("/")[0];
      if (section) return section;
    }

    if (child.type === "folder") {
      const nested = folderSectionSlug(child, baseUrl);
      if (nested !== "section") return nested;
    }
  }

  return "section";
}

export function folderContainsPath(
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

export function resolveFolderSectionSlug(
  item: PageTree.Folder,
  baseUrl: ContentBaseUrl,
): string {
  if (item.index?.url != null) {
    return folderSectionSlugFromUrl(toNavUrl(item.index.url));
  }
  return folderSectionSlug(item, baseUrl);
}

export function resolveFolderDefaultOpen(
  item: PageTree.Folder,
  level: number,
  pathname: string,
): boolean {
  const containsPath = folderContainsPath(item, pathname);
  return containsPath || (level > 1 && (item.defaultOpen ?? false));
}

export function resolveFolderKey(
  item: PageTree.Folder,
  level: number,
  pathname: string,
  sectionSlug: string,
): string {
  const folderUrl = item.index?.url;
  if (level <= 1) return `${sectionSlug}-${pathname}`;
  return `${folderUrl ?? sectionSlug}-${level}`;
}

export function resolveFolderHeaderIcon(
  item: PageTree.Folder,
  level: number,
  baseUrl: ContentBaseUrl,
  sectionSlug: string,
): ReactNode {
  if (level <= 1) {
    return (
      <SidebarIcon
        className="sidebar-section-icon"
        icon={getSectionIconForSlug(toSectionSlug(sectionSlug), baseUrl)}
      />
    );
  }

  const folderUrl = item.index?.url ? toNavUrl(item.index.url) : undefined;
  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;

  return item.icon ?? (folderUrl ? iconResolver(undefined, folderUrl) : undefined);
}
