"use client";

import { RootProvider } from "fumadocs-ui/provider";
import type { ReactNode } from "react";

type DocsRootProviderProps = Readonly<{
  children: ReactNode;
}>;

const searchOptions =
  process.env.NODE_ENV === "development"
    ? { api: "/api/search" as const }
    : { api: "/api/search" as const, type: "static" as const };

export function DocsRootProvider({ children }: DocsRootProviderProps) {
  return (
    <RootProvider
      search={{ options: searchOptions }}
      theme={{ enabled: true, attribute: "class", defaultTheme: "dark" }}
    >
      {children}
    </RootProvider>
  );
}
