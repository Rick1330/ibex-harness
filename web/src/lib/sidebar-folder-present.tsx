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
  firstNavUrlInFolder,
  folderContainsPath,
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

  const nestedUrl = firstNavUrlInFolder(item);
  let folderUrl: ReturnType<typeof toNavUrl> | undefined;
  if (item.index?.url) {
    folderUrl = toNavUrl(item.index.url);
  } else if (nestedUrl) {
    folderUrl = toNavUrl(nestedUrl);
  }
  const iconResolver =
    baseUrl === "/roadmap" ? roadmapNavIconElement : navIconElement;

  return folderUrl ? iconResolver(undefined, folderUrl) : undefined;
}
