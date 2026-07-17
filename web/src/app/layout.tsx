import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ClearMermaidCache } from "@/components/clear-mermaid-cache";
import { DocsRootProvider } from "@/components/docs-root-provider";
import { SearchIndexPrefetch } from "@/components/search-index-prefetch";
import { SiteNavShell } from "@/components/site-nav-shell";
import { ThemeNoFlashScript } from "@/components/theme-no-flash";
import { STATIC_SEARCH_INDEX_URL } from "@/lib/search-index-url";
import {
  SITE_AI_URL,
  SITE_LLMS_URL,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_URL,
} from "@/lib/site-seo";
import "./globals.css";

const isProd = process.env.NODE_ENV === "production";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "IBEX Harness", template: "%s — IBEX Harness" },
  description: SITE_DESCRIPTION,
  keywords: SITE_KEYWORDS,
  applicationName: "IBEX Harness",
  manifest: "/site.webmanifest",
  alternates: {
    types: {
      "text/plain": [
        { url: "/llms.txt", title: "LLM context" },
        { url: "/ai.txt", title: "AI crawler policy" },
      ],
    },
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: SITE_URL,
    siteName: "IBEX Harness",
    title: "IBEX Harness",
    description: SITE_DESCRIPTION,
    images: [
      {
        url: "/brand/android-chrome-512x512.png",
        width: 512,
        height: 512,
        alt: "IBEX Harness",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "IBEX Harness",
    description: SITE_DESCRIPTION,
    images: ["/brand/android-chrome-512x512.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
    },
  },
  other: {
    "llms-txt": SITE_LLMS_URL,
    "ai-txt": SITE_AI_URL,
  },
  icons: {
    icon: [
      { url: "/icon.png", type: "image/png", sizes: "32x32" },
      {
        url: "/brand/icon-dark-scheme.png",
        type: "image/png",
        sizes: "32x32",
        media: "(prefers-color-scheme: dark)",
      },
    ],
    apple: [{ url: "/apple-icon.png", type: "image/png", sizes: "180x180" }],
  },
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className="bg-background text-foreground antialiased">
        <ThemeNoFlashScript />
        <ClearMermaidCache />
        {isProd ? (
          <SearchIndexPrefetch indexUrl={STATIC_SEARCH_INDEX_URL} />
        ) : null}
        <DocsRootProvider>
          <SiteNavShell />
          {children}
        </DocsRootProvider>
      </body>
    </html>
  );
}
