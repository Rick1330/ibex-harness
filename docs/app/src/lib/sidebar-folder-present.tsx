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

function sectionFromChildUrl(url: string, prefix: string): string | undefined {
  const withoutPrefix = url.startsWith(prefix) ? url.slice(prefix.length) : url;
  return withoutPrefix.split("/")[0] || undefined;
}

function sectionFromTreeNode(
  node: PageTree.Node,
  prefix: string,
  baseUrl: ContentBaseUrl,
): string | undefined {
  if (node.type === "page") {
    return sectionFromChildUrl(node.url, prefix);
  }

  if (node.type !== "folder") return undefined;

  if (node.index?.url) {
    const fromIndex = sectionFromChildUrl(toNavUrl(node.index.url), prefix);
    if (fromIndex) return fromIndex;
  }

  for (const child of node.children) {
    const nested = sectionFromTreeNode(child, prefix, baseUrl);
    if (nested) return nested;
  }

  return undefined;
}

function folderSectionSlug(
  item: PageTree.Folder,
  baseUrl: ContentBaseUrl,
): string {
  const prefix = baseUrl === "/docs" ? "/docs/" : "/roadmap/";

  for (const child of item.children) {
    const section = sectionFromTreeNode(child, prefix, baseUrl);
    if (section) return section;
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
  return folderContainsPath(item, pathname) || (level > 1 && (item.defaultOpen ?? false));
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
