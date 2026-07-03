import type { MobileNavData, MobileNavNode } from "@/lib/mobile-nav-data";

export function getSectionTree(
  data: MobileNavData,
  dataKey: "docsTree" | "roadmapTree",
): MobileNavNode[] {
  if (dataKey === "docsTree") return data.docsTree;
  return data.roadmapTree;
}

export function getSectionPages(
  data: MobileNavData,
  dataKey: "blogPosts" | "releasePages" | "benchmarkPages",
): ReadonlyArray<{ url: string; title: string }> {
  if (dataKey === "blogPosts") return data.blogPosts;
  if (dataKey === "benchmarkPages") return data.benchmarkPages;
  return data.releasePages;
}
