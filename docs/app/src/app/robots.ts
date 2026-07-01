import type { MetadataRoute } from "next";

import { DOCS_SITE_URL, MARKETING_SITE_URL } from "@/lib/site-seo";

export const dynamic = "force-static";

const AI_CRAWLERS = [
  "GPTBot",
  "ChatGPT-User",
  "Google-Extended",
  "anthropic-ai",
  "ClaudeBot",
] as const;

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/" },
      ...AI_CRAWLERS.map((userAgent) => ({ userAgent, allow: "/" as const })),
    ],
    sitemap: [`${DOCS_SITE_URL}/sitemap.xml`, `${MARKETING_SITE_URL}/sitemap.xml`],
    host: DOCS_SITE_URL,
  };
}
