import { create, insertMultiple, save } from "@orama/orama";
import { createSearchAPI, type Index } from "fumadocs-core/search/server";

import {
  buildSearchContent,
  shouldIndexSearchPage,
  type SearchablePage,
} from "@/lib/search-content";
import { blogSource, roadmapSource, source } from "@/lib/source";

export { buildSearchContent } from "@/lib/search-content";

function toSimpleIndex(page: SearchablePage): Index {
  const description = page.data.description ?? page.data.excerpt ?? "";
  return {
    url: page.url,
    title: page.data.title ?? page.url,
    description,
    content: buildSearchContent(page),
    keywords: page.data.tags?.join(", "),
  };
}

export function collectSearchPages(): SearchablePage[] {
  const staticPages: SearchablePage[] = [
    {
      url: "/releases",
      data: {
        title: "Changelog",
        description:
          "What shipped in each IBEX Harness release — curated highlights from CHANGELOG.md.",
      },
    },
    // These register routes are emitted by the roadmap page tree but omitted
    // from roadmapSource.getPages() in the current Fumadocs walker output.
    // Their compact, tested summaries keep the critical readiness records
    // discoverable without indexing their dense tables.
    {
      url: "/roadmap/phase-4-multi-provider/findings",
      data: { title: "Phase 4 — Findings Register" },
    },
    {
      url: "/roadmap/phase-4-multi-provider/risks",
      data: { title: "Phase 4 — Risks and Mitigations" },
    },
  ];

  const pages = [
    ...source.getPages(),
    ...blogSource.getPages(),
    ...roadmapSource.getPages(),
    ...staticPages,
  ]
    .filter((page) => shouldIndexSearchPage(page.url))
    .map((page) => ({ url: page.url, data: page.data }));
  return Array.from(new Map(pages.map((page) => [page.url, page])).values());
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
