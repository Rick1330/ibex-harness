"use client";

import {
  create,
  load,
  search as oramaSearch,
  type AnyOrama,
} from "@orama/orama";
import { useEffect, useRef, useState } from "react";

export type DocsSearchResult = {
  type: "page";
  content: string;
  id: string;
  url: string;
};

type SimpleSearchDocument = {
  title?: unknown;
  url?: unknown;
};

type SimpleSearchHit = {
  document: SimpleSearchDocument;
};

/** Map Orama simple-index hits to fumadocs search result rows. */
export function mapSimpleSearchHits(hits: SimpleSearchHit[]): DocsSearchResult[] {
  return hits.map((hit) => ({
    type: "page",
    content: String(hit.document.title ?? ""),
    id: String(hit.document.url ?? ""),
    url: String(hit.document.url ?? ""),
  }));
}

/** Debounce a string value for search input. */
function useDebounce(value: string, delayMs: number): string {
  const [debouncedValue, setDebouncedValue] = useState(value);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (delayMs === 0) {
      setDebouncedValue(value);
      return;
    }

    timer.current = window.setTimeout(() => {
      setDebouncedValue(value);
    }, delayMs);

    return () => {
      if (timer.current !== undefined) {
        window.clearTimeout(timer.current);
      }
    };
  }, [delayMs, value]);

  return delayMs === 0 ? value : debouncedValue;
}

let cachedIndex: Promise<AnyOrama> | undefined;

/** Fetch and cache the baked Orama index at the fixed static path. */
async function loadSearchIndex(): Promise<AnyOrama> {
  if (cachedIndex) return cachedIndex;

  cachedIndex = (async () => {
    const response = await fetch("/search-index.json");
    if (!response.ok) {
      throw new Error(`search index fetch failed: HTTP ${response.status}`);
    }

    const data = await response.json();
    const db = await create({ schema: { _: "string" } });
    await load(db, data);
    return db;
  })().catch((error: unknown) => {
    cachedIndex = undefined;
    throw error;
  });

  return cachedIndex;
}

/** Client-side Orama search for static export (fumadocs 14 static client bug workaround). */
export function useStaticDocsSearch(delayMs = 100) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<DocsSearchResult[] | "empty">("empty");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error>();
  const debouncedQuery = useDebounce(search, delayMs);
  const requestId = useRef(0);

  useEffect(() => {
    if (debouncedQuery.length === 0) {
      requestId.current += 1;
      setResults("empty");
      setIsLoading(false);
      setError(undefined);
      return;
    }

    const currentRequest = ++requestId.current;
    setIsLoading(true);
    setError(undefined);

    void loadSearchIndex()
      .then((db) =>
        oramaSearch(db, {
          term: debouncedQuery,
          tolerance: 1,
          boost: { title: 2 },
        }),
      )
      .then((result) => {
        if (currentRequest !== requestId.current) return;
        const mapped = mapSimpleSearchHits(
          result.hits as SimpleSearchHit[],
        );
        setResults(mapped.length > 0 ? mapped : "empty");
      })
      .catch((err: unknown) => {
        if (currentRequest !== requestId.current) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setResults("empty");
      })
      .finally(() => {
        if (currentRequest === requestId.current) {
          setIsLoading(false);
        }
      });
  }, [debouncedQuery]);

  return { search, setSearch, query: { isLoading, data: results, error } };
}
