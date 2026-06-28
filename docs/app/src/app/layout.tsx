import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { ClearMermaidCache } from "@/components/clear-mermaid-cache";
import {
  DocsRootProvider,
} from "@/components/docs-root-provider";
import { SearchIndexPrefetch } from "@/components/search-index-prefetch";
import { SiteNavShell } from "@/components/site-nav-shell";
import { STATIC_SEARCH_INDEX_URL } from "@/lib/search-index-url";
import "./globals.css";

const isProd = process.env.NODE_ENV === "production";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://docs.ibexharness.com"),
  title: { default: "IBEX Harness Docs", template: "%s — IBEX Harness" },
  description: "Self-hosted LLM proxy with persistent agent memory.",
  manifest: "/site.webmanifest",
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

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-canvas text-text-primary antialiased">
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
