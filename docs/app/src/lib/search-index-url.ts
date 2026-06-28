/** Stable path written by extract-search-index; must match public/_redirects. */
export const STATIC_SEARCH_INDEX_URL = "/search-index.json";

const ALLOWED_SEARCH_INDEX_URLS = new Set<string>([STATIC_SEARCH_INDEX_URL]);

/** Reject dynamic URLs; only the baked static index path is permitted. */
export function resolveAllowedSearchIndexUrl(candidate: string): string {
  if (ALLOWED_SEARCH_INDEX_URLS.has(candidate)) {
    return candidate;
  }

  throw new Error(`search index URL not allowed: ${candidate}`);
}
