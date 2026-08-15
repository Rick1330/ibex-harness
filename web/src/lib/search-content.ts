type SearchTocItem = {
  title?: unknown;
  children?: SearchTocItem[];
};

export type SearchablePageData = {
  title?: string;
  description?: string;
  excerpt?: string;
  tags?: string[];
  toc?: SearchTocItem[];
  structuredData?: {
    contents?: Array<{ content?: string; heading?: string }>;
    headings?: Array<{ content?: string }>;
  };
};

export type SearchablePage = {
  url: string;
  data: SearchablePageData;
};

function collectTocTitles(items: SearchTocItem[] | undefined, out: string[]) {
  if (!items) return;
  for (const item of items) {
    if (typeof item.title === "string" && item.title.trim()) {
      out.push(item.title.trim());
    }
    collectTocTitles(item.children, out);
  }
}

/** Build searchable body text from description, headings, and structured excerpts. */
export function buildSearchContent(page: SearchablePage): string {
  const parts: string[] = [];
  const description = page.data.description ?? page.data.excerpt ?? "";
  if (description) parts.push(description);

  collectTocTitles(page.data.toc, parts);

  const structured = page.data.structuredData;
  if (structured?.headings) {
    for (const heading of structured.headings) {
      if (typeof heading.content === "string" && heading.content.trim()) {
        parts.push(heading.content.trim());
      }
    }
  }
  if (structured?.contents) {
    for (const block of structured.contents) {
      if (typeof block.heading === "string" && block.heading.trim()) {
        parts.push(block.heading.trim());
      }
      if (typeof block.content === "string" && block.content.trim()) {
        // Cap per-block to keep the static index bounded.
        parts.push(block.content.trim().slice(0, 800));
      }
    }
  }

  return parts.join("\n");
}
