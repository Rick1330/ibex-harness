"use client";

import {
  SearchDialog,
  type SharedProps,
} from "fumadocs-ui/components/dialog/search";

import { useStaticDocsSearch } from "@/hooks/use-static-docs-search";
import { STATIC_SEARCH_INDEX_URL } from "@/lib/search-index-url";

type StaticSearchDialogProps = SharedProps & {
  api?: string;
  delayMs?: number;
};

/** Static-export search dialog; bypasses fumadocs 14 simple static client bug. */
export default function StaticSearchDialog({
  api = STATIC_SEARCH_INDEX_URL,
  delayMs,
  ...props
}: StaticSearchDialogProps) {
  const { search, setSearch, query } = useStaticDocsSearch(api, delayMs);

  return (
    <SearchDialog
      search={search}
      onSearchChange={setSearch}
      isLoading={query.isLoading}
      results={query.data}
      {...props}
    />
  );
}
