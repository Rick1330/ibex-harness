"use client";

import { useEffect } from "react";

const searchIndexUrl =
  process.env.NEXT_PUBLIC_SEARCH_INDEX_URL ?? "/search-index.json";

/** Warm the Orama static index during idle time so Cmd+K feels faster. */
export function SearchIndexPrefetch() {
  useEffect(() => {
    const prefetch = () => {
      void fetch(searchIndexUrl, {
        credentials: "same-origin",
        mode: "cors",
      }).catch(() => undefined);
    };

    if ("requestIdleCallback" in window) {
      const id = window.requestIdleCallback(prefetch);
      return () => window.cancelIdleCallback(id);
    }

    const timer = setTimeout(prefetch, 2000);
    return () => clearTimeout(timer);
  }, []);

  return null;
}
