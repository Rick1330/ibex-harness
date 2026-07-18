import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/source", () => ({
  blogSource: {
    getPages: vi.fn(),
  },
}));

import { GET, normalizeSiteUrl } from "@/app/(site)/blog/rss.xml/route";
import { blogSource } from "@/lib/source";

const mockGetPages = vi.mocked(blogSource.getPages);

function fakePost(overrides: {
  title: string;
  date: string;
  url: string;
  excerpt?: string;
  description?: string;
  tags?: string[];
}) {
  return {
    url: overrides.url,
    data: {
      title: overrides.title,
      date: overrides.date,
      excerpt: overrides.excerpt,
      description: overrides.description,
      tags: overrides.tags ?? ["engineering"],
    },
  };
}

describe("blog RSS GET", () => {
  afterEach(() => {
    mockGetPages.mockReset();
    delete process.env.NEXT_PUBLIC_SITE_URL;
  });

  it("normalizes trailing slashes on the site URL", () => {
    expect(normalizeSiteUrl("https://example.com/")).toBe("https://example.com");
    expect(normalizeSiteUrl("https://example.com///")).toBe(
      "https://example.com",
    );
  });

  it("orders items by descending publication date and sets headers", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://example.com/";
    mockGetPages.mockReturnValue([
      fakePost({
        title: "Older",
        date: "2026-01-01",
        url: "/blog/older",
      }),
      fakePost({
        title: "Newer & bold",
        date: "2026-06-01",
        url: "/blog/newer",
        excerpt: "A <snippet>",
      }),
    ] as never);

    const res = await GET();
    const body = await res.text();

    expect(res.headers.get("Content-Type")).toBe(
      "application/rss+xml; charset=utf-8",
    );
    expect(res.headers.get("Cache-Control")).toContain("s-maxage=3600");
    expect(body.indexOf("Newer &amp; bold")).toBeLessThan(
      body.indexOf(">Older<"),
    );
    expect(body).toContain("https://example.com/blog/newer");
    expect(body).toContain("A &lt;snippet&gt;");
    expect(body).toContain("<link>https://example.com/blog</link>");
  });

  it("emits a valid empty channel when there are no posts", async () => {
    mockGetPages.mockReturnValue([]);
    const res = await GET();
    const body = await res.text();

    expect(body).toContain("<channel>");
    expect(body).toContain("</channel>");
    expect(body).not.toContain("<item>");
  });
});
