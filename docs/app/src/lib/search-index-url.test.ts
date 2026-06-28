import { describe, expect, it } from "vitest";

import {
  STATIC_SEARCH_INDEX_URL,
  resolveAllowedSearchIndexUrl,
} from "@/lib/search-index-url";

describe("resolveAllowedSearchIndexUrl", () => {
  it("allows the baked static index path", () => {
    expect(resolveAllowedSearchIndexUrl(STATIC_SEARCH_INDEX_URL)).toBe(
      STATIC_SEARCH_INDEX_URL,
    );
  });

  it("rejects arbitrary URLs", () => {
    expect(() => resolveAllowedSearchIndexUrl("https://evil.example/index.json"))
      .toThrow(/not allowed/);
  });
});
