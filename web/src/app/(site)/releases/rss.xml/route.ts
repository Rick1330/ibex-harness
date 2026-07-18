import { formatChangelogDate } from "@/lib/changelog/grouping";
import { readReleasesFromChangelog } from "@/lib/changelog/read-changelog";

export const dynamic = "force-static";

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export async function GET() {
  const site = process.env.NEXT_PUBLIC_SITE_URL ?? "https://ibexharness.com";
  const releases = readReleasesFromChangelog();

  const items = releases
    .map((release) => {
      const link = `${site}/releases#v${release.version}`;
      const title = `v${release.version}${release.summary ? ` — ${release.summary}` : ""}`;
      const description =
        release.summary ??
        `${release.type} release${release.date ? ` on ${formatChangelogDate(release.date)}` : ""}`;
      return `    <item>
      <title>${escapeXml(title)}</title>
      <link>${escapeXml(link)}</link>
      <guid>${escapeXml(link)}</guid>
      <pubDate>${release.date ? new Date(release.date).toUTCString() : new Date().toUTCString()}</pubDate>
      <category>${escapeXml(release.type)}</category>
      <description>${escapeXml(description)}</description>
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>IBEX Harness Changelog</title>
    <link>${escapeXml(`${site}/releases`)}</link>
    <description>What shipped in each IBEX Harness release.</description>
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
