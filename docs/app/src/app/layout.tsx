import type { Metadata } from "next";
import { RootProvider } from "fumadocs-ui/provider";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import "./globals.css";

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
      className={`dark ${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="bg-canvas text-text-primary antialiased">
        <RootProvider
          search={{ options: { api: "/api/search" } }}
          theme={{ enabled: true, attribute: "class", defaultTheme: "dark" }}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
