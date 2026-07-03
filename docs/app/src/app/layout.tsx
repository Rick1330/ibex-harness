import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { BenchmarkDataPrefetch } from "@/components/benchmarks/benchmark-data-prefetch";
import { BenchmarkProvider } from "@/components/benchmarks/benchmark-provider";
import { ClearMermaidCache } from "@/components/clear-mermaid-cache";
import {
  DocsRootProvider,
} from "@/components/docs-root-provider";
import { SearchIndexPrefetch } from "@/components/search-index-prefetch";
import { SiteNavShell } from "@/components/site-nav-shell";
import { STATIC_SEARCH_INDEX_URL } from "@/lib/search-index-url";
import {
  DOCS_AI_URL,
  DOCS_LLMS_URL,
  DOCS_SITE_URL,
  MARKETING_AI_URL,
  MARKETING_LLMS_URL,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
} from "@/lib/site-seo";
import "./globals.css";

const isProd = process.env.NODE_ENV === "production";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(DOCS_SITE_URL),
  title: { default: "IBEX Harness Docs", template: "%s — IBEX Harness" },
  description: SITE_DESCRIPTION,
  keywords: SITE_KEYWORDS,
  applicationName: "IBEX Harness Docs",
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
    url: DOCS_SITE_URL,
    siteName: "IBEX Harness Docs",
    title: "IBEX Harness Docs",
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
    title: "IBEX Harness Docs",
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
    "llms-txt": DOCS_LLMS_URL,
    "ai-txt": DOCS_AI_URL,
    "marketing-llms-txt": MARKETING_LLMS_URL,
    "marketing-ai-txt": MARKETING_AI_URL,
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
    <html
      lang="en"
      data-scroll-behavior="smooth"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-canvas text-text-primary antialiased">
        <ClearMermaidCache />
        {isProd ? (
          <SearchIndexPrefetch indexUrl={STATIC_SEARCH_INDEX_URL} />
        ) : null}
        <DocsRootProvider>
          <BenchmarkProvider>
            <SiteNavShell />
            <BenchmarkDataPrefetch />
            {children}
          </BenchmarkProvider>
        </DocsRootProvider>
      </body>
    </html>
  );
}
