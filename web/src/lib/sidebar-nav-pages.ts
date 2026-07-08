import type { PageTree } from "fumadocs-core/server";
import type { ReactNode } from "react";

export type NavPage = {
  name: ReactNode;
  url: string;
  icon?: ReactNode;
};

export function normalizeNavUrl(url: string): string {
  let normalized = url;
  if (normalized.length > 1 && normalized.endsWith("/")) {
    normalized = normalized.slice(0, -1);
  }
  if (normalized.endsWith("/index")) {
    normalized = normalized.slice(0, -6) || "/";
  }
  return normalized;
}

/** Match fumadocs-ui footer active-page detection (exact URL, no nested prefix). */
export function navUrlsMatch(url: string, pathname: string): boolean {
  return normalizeNavUrl(url) === normalizeNavUrl(pathname);
}

function appendNavPage(list: NavPage[], seen: Set<string>, page: NavPage) {
  const url = normalizeNavUrl(page.url);
  if (seen.has(url)) return;
  seen.add(url);
  list.push({ name: page.name, url: page.url, icon: page.icon });
}

export function flattenPageTree(nodes: PageTree.Node[]): NavPage[] {
  const list: NavPage[] = [];
  const seen = new Set<string>();

  function walk(treeNodes: PageTree.Node[]) {
    for (const node of treeNodes) {
      if (node.type === "folder") {
        if (node.index && !node.index.external) {
          appendNavPage(list, seen, node.index);
        }
        walk(node.children);
        continue;
      }

      if (node.type === "page" && !node.external) {
        appendNavPage(list, seen, node);
      }
    }
  }

  walk(nodes);
  return list;
}

export function adjacentNavPages(
  pages: NavPage[],
  pathname: string,
): { previous?: NavPage; next?: NavPage } {
  const index = pages.findIndex((page) => navUrlsMatch(page.url, pathname));
  if (index === -1) return {};

  let previousIndex = index - 1;
  while (
    previousIndex >= 0 &&
    navUrlsMatch(pages[previousIndex].url, pathname)
  ) {
    previousIndex -= 1;
  }

  let nextIndex = index + 1;
  while (
    nextIndex < pages.length &&
    navUrlsMatch(pages[nextIndex].url, pathname)
  ) {
    nextIndex += 1;
  }

  return {
    previous: previousIndex >= 0 ? pages[previousIndex] : undefined,
    next: nextIndex < pages.length ? pages[nextIndex] : undefined,
  };
}
