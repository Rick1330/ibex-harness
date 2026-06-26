import { createSearchAPI, type AdvancedIndex } from "fumadocs-core/search/server";

import { blogSource, releasesSource, roadmapSource, source } from "@/lib/source";

type SearchablePage = {
  url: string;
  data: {
    title?: string;
    description?: string;
    excerpt?: string;
    structuredData?: AdvancedIndex["structuredData"];
    tags?: string[];
  };
};

function toIndex(page: SearchablePage): AdvancedIndex {
  return {
    id: page.url,
    url: page.url,
    title: page.data.title ?? page.url,
    description: page.data.description ?? page.data.excerpt,
    keywords: page.data.tags ? page.data.tags.join(", ") : undefined,
    structuredData: page.data.structuredData ?? { headings: [], contents: [] },
  };
}

export const search = createSearchAPI("advanced", {
  indexes: () => [
    ...source.getPages(),
    ...blogSource.getPages(),
    ...releasesSource.getPages(),
    ...roadmapSource.getPages(),
  ].map((page) => toIndex(page as SearchablePage)),
});
