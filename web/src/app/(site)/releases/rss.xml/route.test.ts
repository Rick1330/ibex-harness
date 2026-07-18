import { afterEach, describe, expect, it, vi } from "vitest";

import { makeRelease } from "@/components/changelog/test-fixtures";

vi.mock("@/lib/changelog/read-changelog", () => ({
  readReleasesFromChangelog: vi.fn(),
}));

import { GET } from "@/app/(site)/releases/rss.xml/route";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

const mockRead = vi.mocked(readReleasesFromChangelog);

describe("releases RSS GET", () => {
  afterEach(() => {
    mockRead.mockReset();
    delete process.env.NEXT_PUBLIC_SITE_URL;
  });

  it("omits invalid pubDate, escapes XML, and keeps stable GUIDs", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://example.com/";
    mockRead.mockReturnValue([
      makeRelease({
        version: "0.2.0",
        date: "not-a-date",
        summary: "Ship <fast> & safe",
      }),
      makeRelease({
        version: "0.1.0",
        date: "2026-01-15",
        summary: null,
      }),
    ]);

    const res = await GET();
    const body = await res.text();

    expect(res.headers.get("Content-Type")).toBe(
      "application/rss+xml; charset=utf-8",
    );
    expect(body).toContain("https://example.com/releases#v0.2.0");
    expect(body).toContain("Ship &lt;fast&gt; &amp; safe");
    expect(body).toContain("<guid>https://example.com/releases#v0.2.0</guid>");
    // invalid date → no pubDate on that item
    const v2Block = body.slice(
      body.indexOf("#v0.2.0"),
      body.indexOf("#v0.1.0"),
    );
    expect(v2Block).not.toContain("<pubDate>");
    expect(body).toContain("<pubDate>");
  });

  it("emits an empty channel when there are no releases", async () => {
    mockRead.mockReturnValue([]);
    const res = await GET();
    const body = await res.text();
    expect(body).not.toContain("<item>");
    expect(body).toContain("<channel>");
  });
});
