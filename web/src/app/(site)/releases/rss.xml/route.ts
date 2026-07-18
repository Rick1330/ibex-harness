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

function normalizeSiteUrl(raw: string): string {
  return raw.replace(/\/+$/, "");
}

function rssPubDate(date: string | null | undefined): string | null {
  if (!date) return null;
  const parsed = new Date(date);
  if (!Number.isFinite(parsed.getTime())) return null;
  return parsed.toUTCString();
}

function releaseDescription(
  release: ReturnType<typeof readReleasesFromChangelog>[number],
): string {
  if (release.summary) return release.summary;
  if (!release.date) return `${release.type} release`;
  return `${release.type} release on ${formatChangelogDate(release.date)}`;
}

function buildReleaseItem(
  site: string,
  release: ReturnType<typeof readReleasesFromChangelog>[number],
): string {
  const link = `${site}/releases#v${release.version}`;
  const title = release.summary
    ? `v${release.version} — ${release.summary}`
    : `v${release.version}`;
  const description = releaseDescription(release);
  const pubDate = rssPubDate(release.date);
  const lines = [
    "    <item>",
    `      <title>${escapeXml(title)}</title>`,
    `      <link>${escapeXml(link)}</link>`,
    `      <guid>${escapeXml(link)}</guid>`,
  ];
  if (pubDate) {
    lines.push(`      <pubDate>${pubDate}</pubDate>`);
  }
  lines.push(
    `      <category>${escapeXml(release.type)}</category>`,
    `      <description>${escapeXml(description)}</description>`,
    "    </item>",
  );
  return lines.join("\n");
}

export async function GET() {
  const site = normalizeSiteUrl(
    process.env.NEXT_PUBLIC_SITE_URL ?? "https://ibexharness.com",
  );
  const releasesUrl = `${site}/releases`;
  const releases = readReleasesFromChangelog();
  const items = releases.map((release) => buildReleaseItem(site, release)).join("\n");

  const xml = [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<rss version="2.0">`,
    `  <channel>`,
    `    <title>IBEX Harness Changelog</title>`,
    `    <link>${escapeXml(releasesUrl)}</link>`,
    `    <description>What shipped in each IBEX Harness release.</description>`,
    items,
    `  </channel>`,
    `</rss>`,
  ].join("\n");

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
