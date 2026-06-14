import type { PageTree } from "fumadocs-core/server";
import type { ReactNode } from "react";

export type NavPage = {
  name: ReactNode;
  url: string;
};

export function normalizeNavUrl(url: string): string {
  if (url.length > 1 && url.endsWith("/")) {
    return url.slice(0, -1);
  }
  return url;
}

function appendNavPage(list: NavPage[], seen: Set<string>, page: NavPage) {
  const url = normalizeNavUrl(page.url);
  if (seen.has(url)) return;
  seen.add(url);
  list.push({ name: page.name, url });
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
  const current = normalizeNavUrl(pathname);
  const index = pages.findIndex((page) => normalizeNavUrl(page.url) === current);
  if (index === -1) return {};

  const previous = pages[index - 1];
  const next = pages[index + 1];

  return {
    previous:
      previous && normalizeNavUrl(previous.url) !== current ? previous : undefined,
    next: next && normalizeNavUrl(next.url) !== current ? next : undefined,
  };
}
