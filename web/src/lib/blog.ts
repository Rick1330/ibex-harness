export const BLOG_CATEGORIES = [
  "Engineering",
  "Product",
  "Research",
] as const;

export type BlogCategory = (typeof BLOG_CATEGORIES)[number];

const PRODUCT_TAGS = new Set([
  "product",
  "announcement",
  "docs",
  "roadmap",
  "launch",
]);

const RESEARCH_TAGS = new Set([
  "research",
  "benchmark",
  "memory",
  "guide",
]);

/** Map post tags → editorial category chips (DESIGN_GUIDE.md §14.1). */
export function resolveBlogCategory(tags?: ReadonlyArray<string>): BlogCategory {
  const normalized = (tags ?? []).map((tag) => tag.toLowerCase());
  if (normalized.some((tag) => PRODUCT_TAGS.has(tag))) return "Product";
  if (normalized.some((tag) => RESEARCH_TAGS.has(tag))) return "Research";
  return "Engineering";
}

export function formatBlogDate(date: string | Date): string {
  const value = typeof date === "string" ? new Date(date) : date;
  return value.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });
}

export function formatBlogDateLong(date: string | Date): string {
  const value = typeof date === "string" ? new Date(date) : date;
  return value.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function blogYear(date: string | Date): number {
  const value = typeof date === "string" ? new Date(date) : date;
  return value.getUTCFullYear();
}

export type BlogIndexItem = {
  url: string;
  title: string;
  date: string;
  excerpt?: string;
  tags?: string[];
  readingTime?: string;
  author?: string;
  authorUrl?: string;
  category: BlogCategory;
};

/** Group archive rows by year, newest year first. */
export function groupPostsByYear(
  posts: ReadonlyArray<BlogIndexItem>,
): Array<{ year: number; posts: BlogIndexItem[] }> {
  const map = new Map<number, BlogIndexItem[]>();
  for (const post of posts) {
    const year = blogYear(post.date);
    const bucket = map.get(year);
    if (bucket) bucket.push(post);
    else map.set(year, [post]);
  }
  return [...map.entries()]
    .sort(([a], [b]) => b - a)
    .map(([year, yearPosts]) => ({ year, posts: yearPosts }));
}

/** Italicize the last word of a display title (guide: one italic word). */
export function titleWithItalicTail(title: string): {
  lead: string;
  italic: string;
} {
  const trimmed = title.trim();
  const parts = trimmed.split(/\s+/);
  if (parts.length < 2) return { lead: "", italic: trimmed };
  const italic = parts.at(-1) ?? trimmed;
  const lead = parts.slice(0, -1).join(" ");
  return { lead, italic };
}
