"use client";

import dynamic from "next/dynamic";
import { RootProvider } from "fumadocs-ui/provider";
import type { ReactNode } from "react";

import { STATIC_SEARCH_INDEX_URL } from "@/lib/search-index-url";

const StaticSearchDialog = dynamic(
  () => import("@/components/static-search-dialog"),
  { ssr: false },
);

const isProd = process.env.NODE_ENV === "production";
const searchOptions = isProd
  ? { type: "static" as const, api: STATIC_SEARCH_INDEX_URL }
  : { type: "fetch" as const, api: "/api/search" };

type DocsRootProviderProps = Readonly<{
  children: ReactNode;
}>;

/** Root fumadocs provider; production uses a client-only static search dialog. */
export function DocsRootProvider({ children }: DocsRootProviderProps) {
  return (
    <RootProvider
      search={{
        ...(isProd ? { SearchDialog: StaticSearchDialog } : {}),
        options: searchOptions,
      }}
      theme={{
        enabled: true,
        attribute: "class",
        defaultTheme: "system",
        enableSystem: true,
        storageKey: "ibex-theme",
      }}
    >
      {children}
    </RootProvider>
  );
}
