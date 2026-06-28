import { create, insertMultiple, save } from "@orama/orama";
import { createSearchAPI, type Index } from "fumadocs-core/search/server";

import { blogSource, releasesSource, roadmapSource, source } from "@/lib/source";

type SearchablePage = {
  url: string;
  data: {
    title?: string;
    description?: string;
    excerpt?: string;
    tags?: string[];
  };
};

/** Roadmap milestone specs inflate the index; keep hub and phase overviews only. */
function shouldIndexPage(url: string): boolean {
  if (url.includes("/_design")) return false;
  if (!url.startsWith("/roadmap")) return true;
  if (url === "/roadmap" || url === "/roadmap/current-state") return true;
  if (url.includes("/milestones/")) return false;
  return true;
}

function toSimpleIndex(page: SearchablePage): Index {
  const description = page.data.description ?? page.data.excerpt ?? "";
  return {
    url: page.url,
    title: page.data.title ?? page.url,
    description,
    content: description,
    keywords: page.data.tags?.join(", "),
  };
}

function collectSearchPages(): SearchablePage[] {
  return [
    ...source.getPages(),
    ...blogSource.getPages(),
    ...releasesSource.getPages(),
    ...roadmapSource.getPages(),
  ]
    .filter((page) => shouldIndexPage(page.url))
    .map((page) => page as SearchablePage);
}

const searchOptions = {
  indexes: () => collectSearchPages().map(toSimpleIndex),
};

export const search = createSearchAPI("simple", searchOptions);

const simpleSchema = {
  url: "string",
  title: "string",
  description: "string",
  content: "string",
  keywords: "string",
} as const;

/** Orama v2 save() is async; fumadocs-core spreads it without await. */
export async function exportStaticSearchIndex() {
  const items = searchOptions.indexes();
  const db = await create({ schema: simpleSchema });
  await insertMultiple(
    db,
    items.map((page) => ({
      title: page.title,
      description: page.description,
      url: page.url,
      content: page.content,
      keywords: page.keywords,
    })),
  );

  return {
    type: "simple" as const,
    ...(await save(db)),
  };
}
