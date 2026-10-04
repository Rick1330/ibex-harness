import type { TOCItemType } from "fumadocs-core/toc";

/** H2/H3 only — shared by desktop rail and mobile TOC bar. */
export function filterTocHeadings(items: TOCItemType[]): TOCItemType[] {
  return items.filter((item) => item.depth === 2 || item.depth === 3);
}
