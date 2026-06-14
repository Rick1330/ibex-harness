import type { PageTree } from "fumadocs-core/server";
import type { ReactNode } from "react";

import {
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

import {
  folderContainsPath,
  resolveFolderSectionSlug,
} from "@/lib/sidebar-folder-slug";

export { folderContainsPath, resolveFolderSectionSlug } from "@/lib/sidebar-folder-slug";

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
