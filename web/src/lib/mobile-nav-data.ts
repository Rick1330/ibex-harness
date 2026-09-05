import type { PageTree } from "fumadocs-core/server";

import { BENCHMARK_NAV_PAGES, benchmarkPageTree } from "@/lib/benchmark-page-tree";
import { pageTreeLabel } from "@/lib/page-tree-label";
import { blogSource, roadmapSource, source } from "@/lib/source";

export type MobileNavPage = Readonly<{
  kind: "page";
  name: string;
  url: string;
  external?: boolean;
}>;

export type MobileNavFolder = Readonly<{
  kind: "folder";
  name: string;
  children: MobileNavNode[];
}>;

export type MobileNavNode = MobileNavPage | MobileNavFolder;

export type MobileNavData = Readonly<{
  docsTree: MobileNavNode[];
  roadmapTree: MobileNavNode[];
  benchmarkTree: MobileNavNode[];
  blogPosts: ReadonlyArray<{ url: string; title: string }>;
  releasePages: ReadonlyArray<{ url: string; title: string }>;
  /** Flat leaf list kept for sitemap / legacy callers. */
  benchmarkPages: ReadonlyArray<{ url: string; title: string }>;
}>;

function serializePageNode(node: PageTree.Item): MobileNavPage {
  return {
    kind: "page",
    name: pageTreeLabel(node.name),
    url: node.url,
    external: node.external,
  };
}

function isDuplicateFolderIndex(
  child: MobileNavNode,
  indexUrl: string | undefined,
): boolean {
  if (child.kind !== "page") {
    return false;
  }
  if (indexUrl === undefined) {
    return false;
  }
  return child.url === indexUrl;
}

function serializeFolderNode(node: PageTree.Folder): MobileNavFolder {
  const children: MobileNavNode[] = [];
  const indexUrl = node.index?.url;

  if (node.index) {
    children.push(serializePageNode(node.index));
  }

  for (const child of serializeNodes(node.children)) {
    if (isDuplicateFolderIndex(child, indexUrl)) {
      continue;
    }
    children.push(child);
  }

  return {
    kind: "folder",
    name: pageTreeLabel(node.name),
    children,
  };
}

function serializeNodes(nodes: PageTree.Node[]): MobileNavNode[] {
  const result: MobileNavNode[] = [];

  for (const node of nodes) {
    if (node.type === "separator") continue;

    if (node.type === "folder") {
      result.push(serializeFolderNode(node));
      continue;
    }

    result.push(serializePageNode(node));
  }

  return result;
}

function postTimestamp(date: unknown): number {
  const raw =
    typeof date === "string" || typeof date === "number"
      ? String(date)
      : "";
  const ms = new Date(raw || 0).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

let cachedMobileNavData: MobileNavData | undefined;

export function getMobileNavData(): MobileNavData {
  if (cachedMobileNavData) {
    return cachedMobileNavData;
  }

  const blogPosts = blogSource
    .getPages()
    .sort((a, b) => postTimestamp(b.data.date) - postTimestamp(a.data.date))
    .map((page) => ({
      url: page.url,
      title: String(page.data.title),
    }));

  const releasePages = [{ url: "/releases", title: "Changelog" }];

  cachedMobileNavData = {
    docsTree: serializeNodes(source.getPageTree().children),
    roadmapTree: serializeNodes(roadmapSource.getPageTree().children),
    benchmarkTree: serializeNodes(benchmarkPageTree.children),
    blogPosts,
    releasePages,
    benchmarkPages: BENCHMARK_NAV_PAGES.map((page) => ({
      url: page.url,
      title: page.name,
    })),
  };

  return cachedMobileNavData;
}
