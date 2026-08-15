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

const STRUCTURED_CONTENT_CAP = 800;

function appendText(parts: string[], value: unknown, limit?: number) {
  if (typeof value !== "string") return;
  const text = value.trim();
  if (!text) return;
  parts.push(limit === undefined ? text : text.slice(0, limit));
}

function collectTocTitles(items: SearchTocItem[] | undefined, out: string[]) {
  if (!items) return;
  for (const item of items) {
    appendText(out, item.title);
    collectTocTitles(item.children, out);
  }
}

function collectStructuredContent(
  structured: SearchablePageData["structuredData"],
  parts: string[],
) {
  if (!structured) return;
  for (const heading of structured.headings ?? []) {
    appendText(parts, heading.content);
  }
  for (const block of structured.contents ?? []) {
    appendText(parts, block.heading);
    appendText(parts, block.content, STRUCTURED_CONTENT_CAP);
  }
}

/** Build searchable body text from description, headings, and structured excerpts. */
export function buildSearchContent(page: SearchablePage): string {
  const parts: string[] = [];
  appendText(parts, page.data.description ?? page.data.excerpt ?? "");
  collectTocTitles(page.data.toc, parts);
  collectStructuredContent(page.data.structuredData, parts);
  return parts.join("\n");
}
