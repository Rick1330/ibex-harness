import type { PageTree } from "fumadocs-core/server";

import {
  contentPathFromUrl,
  folderSectionSlugFromUrl,
  type ContentBaseUrl,
} from "@/lib/sidebar-icon-resolvers";
import { toNavUrl } from "@/lib/sidebar-icons";

export function firstNavUrlInFolder(folder: PageTree.Folder): string | undefined {
  for (const child of folder.children) {
    if (child.type === "page") return child.url;
    if (child.type !== "folder") continue;

    if (child.index?.url) return child.index.url;

    const nested = firstNavUrlInFolder(child);
    if (nested) return nested;
  }

  return undefined;
}

export function resolveFolderSectionSlug(
  item: PageTree.Folder,
  baseUrl: ContentBaseUrl,
): string {
  if (item.index?.url != null) {
    return folderSectionSlugFromUrl(toNavUrl(item.index.url));
  }

  const url = firstNavUrlInFolder(item);
  if (!url) return "section";

  const path = contentPathFromUrl(toNavUrl(url), baseUrl);
  return path.split("/")[0] || "section";
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
