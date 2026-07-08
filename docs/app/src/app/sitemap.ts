import type { MetadataRoute } from "next";

import { BENCHMARK_NAV_PAGES } from "@/lib/benchmark-page-tree";
import { blogSource, roadmapSource, source } from "@/lib/source";
import { SITE_URL } from "@/lib/site-seo";

export const dynamic = "force-static";

/** Align with search index policy — skip milestone leaf pages and internal paths. */
function shouldIndexPage(url: string): boolean {
  if (url.includes("/_design")) return false;
  if (!url.startsWith("/roadmap")) return true;
  if (url === "/roadmap" || url === "/roadmap/current-state") return true;
  if (url.includes("/milestones/")) return false;
  return true;
}

function toSitemapEntry(
  url: string,
  priority?: number,
): MetadataRoute.Sitemap[number] {
  const resolvedPriority =
    priority ?? (url === "/" ? 1.0 : url.startsWith("/docs") ? 0.8 : 0.6);
  return {
    url: `${SITE_URL}${url}`,
    changeFrequency: "weekly",
    priority: resolvedPriority,
  };
}

export default function sitemap(): MetadataRoute.Sitemap {
  const staticBenchmarkPages = BENCHMARK_NAV_PAGES.map((page) => page.url);
  const staticCorePages = ["/", "/releases"];
  const pages = [
    ...source.getPages(),
    ...blogSource.getPages(),
    ...roadmapSource.getPages(),
  ]
    .filter((page) => shouldIndexPage(page.url))
    .map((page) => toSitemapEntry(page.url));

  return [
    ...pages,
    ...staticCorePages.map((url) => toSitemapEntry(url)),
    ...staticBenchmarkPages.map((url) => toSitemapEntry(url)),
  ];
}
