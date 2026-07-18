import { resolveBlogCategory } from "@/lib/blog";
import { blogSource } from "@/lib/source";

export const dynamic = "force-static";

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

/** Strip trailing slashes so feed links/GUIDs stay canonical. */
export function normalizeSiteUrl(raw: string): string {
  return raw.replace(/\/+$/, "");
}

export async function GET() {
  const site = normalizeSiteUrl(
    process.env.NEXT_PUBLIC_SITE_URL ?? "https://ibexharness.com",
  );
  const blogUrl = `${site}/blog`;
  const posts = blogSource
    .getPages()
    .sort(
      (a, b) =>
        new Date(String(b.data.date)).getTime() -
        new Date(String(a.data.date)).getTime(),
    );

  const items = posts
    .map((post) => {
      const link = `${site}${post.url}`;
      const description = post.data.excerpt ?? post.data.description ?? "";
      const category = resolveBlogCategory(post.data.tags);
      return `    <item>
      <title>${escapeXml(post.data.title)}</title>
      <link>${escapeXml(link)}</link>
      <guid>${escapeXml(link)}</guid>
      <pubDate>${new Date(String(post.data.date)).toUTCString()}</pubDate>
      <category>${escapeXml(category)}</category>
      <description>${escapeXml(description)}</description>
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>IBEX Harness Blog</title>
    <link>${escapeXml(blogUrl)}</link>
    <description>Long-form writing about agent infrastructure, memory, and running LLMs in production.</description>
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
