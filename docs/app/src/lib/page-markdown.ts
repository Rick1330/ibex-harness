const FRONTMATTER_PATTERN = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/;

/** Strip YAML frontmatter from raw MDX source text. */
export function stripMdxFrontmatter(raw: string): string {
  return raw.replace(FRONTMATTER_PATTERN, "").trimStart();
}

type PageWithContent = Readonly<{
  data: Readonly<{
    content: string;
  }>;
}>;

/** Return markdown body suitable for clipboard copy (no frontmatter). */
export function getPageMarkdownBody(page: PageWithContent): string {
  return stripMdxFrontmatter(page.data.content);
}
