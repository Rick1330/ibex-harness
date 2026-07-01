import type { MetadataRoute } from "next";

import { blogSource, releasesSource, roadmapSource, source } from "@/lib/source";
import { DOCS_SITE_URL } from "@/lib/site-seo";

export const dynamic = "force-static";

/** Align with search index policy — skip milestone leaf pages and internal paths. */
function shouldIndexPage(url: string): boolean {
  if (url.includes("/_design")) return false;
  if (!url.startsWith("/roadmap")) return true;
  if (url === "/roadmap" || url === "/roadmap/current-state") return true;
  if (url.includes("/milestones/")) return false;
  return true;
}

function toSitemapEntry(url: string): MetadataRoute.Sitemap[number] {
  const priority = url.startsWith("/docs") ? 0.8 : 0.6;
  return {
    url: `${DOCS_SITE_URL}${url}`,
    changeFrequency: "weekly",
    priority,
  };
}

export default function sitemap(): MetadataRoute.Sitemap {
  const pages = [
    ...source.getPages(),
    ...blogSource.getPages(),
    ...releasesSource.getPages(),
    ...roadmapSource.getPages(),
  ]
    .filter((page) => shouldIndexPage(page.url))
    .map((page) => toSitemapEntry(page.url));

  return pages;
}
