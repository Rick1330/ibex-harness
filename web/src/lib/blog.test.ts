import { describe, expect, it } from "vitest";

import {
  groupPostsByYear,
  resolveBlogCategory,
  titleWithItalicTail,
} from "@/lib/blog";

describe("resolveBlogCategory", () => {
  it("maps product-ish tags to Product", () => {
    expect(resolveBlogCategory(["announcement", "phase-1"])).toBe("Product");
  });

  it("maps research-ish tags to Research", () => {
    expect(resolveBlogCategory(["memory", "architecture"])).toBe("Research");
  });

  it("defaults to Engineering", () => {
    expect(resolveBlogCategory(["architecture", "security"])).toBe(
      "Engineering",
    );
  });
});

describe("titleWithItalicTail", () => {
  it("italicizes the last word", () => {
    expect(titleWithItalicTail("Putting agent memory at the proxy")).toEqual({
      lead: "Putting agent memory at the",
      italic: "proxy",
    });
  });
});

describe("groupPostsByYear", () => {
  it("groups newest year first", () => {
    const groups = groupPostsByYear([
      {
        url: "/a",
        title: "A",
        date: "2025-01-01",
        category: "Engineering",
      },
      {
        url: "/b",
        title: "B",
        date: "2026-06-01",
        category: "Product",
      },
    ]);
    expect(groups.map((g) => g.year)).toEqual([2026, 2025]);
  });
});
