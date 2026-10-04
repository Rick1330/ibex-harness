"use client";

import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SharedProps,
} from "fumadocs-ui/components/dialog/search";

import { useStaticDocsSearch } from "@/hooks/use-static-docs-search";
import {
  STATIC_SEARCH_INDEX_URL,
  resolveAllowedSearchIndexUrl,
} from "@/lib/search-index-url";

type StaticSearchDialogProps = SharedProps & {
  api?: string;
  delayMs?: number;
};

/** Static-export search dialog; bypasses fumadocs static client bugs with a local Orama index. */
export default function StaticSearchDialog({
  api = STATIC_SEARCH_INDEX_URL,
  delayMs,
  ...props
}: StaticSearchDialogProps) {
  resolveAllowedSearchIndexUrl(api);
  const { search, setSearch, query } = useStaticDocsSearch(delayMs);

  return (
    <SearchDialog
      search={search}
      onSearchChange={setSearch}
      isLoading={query.isLoading}
      {...props}
    >
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList items={query.data !== "empty" ? query.data : null} />
      </SearchDialogContent>
    </SearchDialog>
  );
}
