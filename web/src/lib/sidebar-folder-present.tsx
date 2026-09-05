import type { PageTree } from "fumadocs-core/server";
import type { ReactNode } from "react";

import type { ContentBaseUrl } from "@/lib/sidebar-icon-resolvers";
import {
  getBenchmarkFolderIconForName,
  getSectionIconForSlug,
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
  if (folderContainsPath(item, pathname)) {
    return true;
  }
  return level > 1 && (item.defaultOpen ?? false);
}

function resolveBenchmarkFolderIcon(item: PageTree.Folder): ReactNode {
  const name = typeof item.name === "string" ? item.name : String(item.name);
  return (
    <SidebarIcon
      className="sidebar-section-icon"
      icon={getBenchmarkFolderIconForName(name)}
    />
  );
}

function resolveDocsOrRoadmapFolderIcon(
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

export function resolveFolderHeaderIcon(
  item: PageTree.Folder,
  level: number,
  baseUrl: ContentBaseUrl,
  sectionSlug: string,
): ReactNode {
  if (baseUrl === "/benchmarks") {
    return resolveBenchmarkFolderIcon(item);
  }
  return resolveDocsOrRoadmapFolderIcon(item, level, baseUrl, sectionSlug);
}
