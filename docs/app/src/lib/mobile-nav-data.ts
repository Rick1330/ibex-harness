import type { PageTree } from "fumadocs-core/server";

import { blogSource, releasesSource, roadmapSource, source } from "@/lib/source";

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
  blogPosts: ReadonlyArray<{ url: string; title: string }>;
  releasePages: ReadonlyArray<{ url: string; title: string }>;
}>;

function serializePageNode(node: PageTree.Item): MobileNavPage {
  return {
    kind: "page",
    name: String(node.name),
    url: node.url,
    external: node.external,
  };
}

function serializeFolderNode(node: PageTree.Folder): MobileNavFolder {
  const children: MobileNavNode[] = [];

  if (node.index) {
    children.push(serializePageNode(node.index));
  }

  children.push(...serializeNodes(node.children));

  return {
    kind: "folder",
    name: String(node.name),
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

  const releasePages = releasesSource
    .getPages()
    .sort((a, b) => postTimestamp(b.data.date) - postTimestamp(a.data.date))
    .map((page) => ({
      url: page.url,
      title: String(page.data.title ?? page.data.version ?? page.url),
    }));

  cachedMobileNavData = {
    docsTree: serializeNodes(source.getPageTree().children),
    roadmapTree: serializeNodes(roadmapSource.getPageTree().children),
    blogPosts,
    releasePages,
  };

  return cachedMobileNavData;
}
