import type { Metadata } from "next";
import { RootProvider } from "fumadocs-ui/provider";
import { JetBrains_Mono } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { ClearMermaidCache } from "@/components/clear-mermaid-cache";
import { SiteNav } from "@/components/site-nav";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://docs.ibexharness.com"),
  title: { default: "IBEX Harness Docs", template: "%s — IBEX Harness" },
  description: "Self-hosted LLM proxy with persistent agent memory.",
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
        <RootProvider
          search={{ options: { api: "/api/search" } }}
          theme={{ enabled: true, attribute: "class", defaultTheme: "dark" }}
        >
          <SiteNav />
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
