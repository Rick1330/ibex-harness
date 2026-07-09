"use client";

import { useEffect } from "react";

/** Warm the Orama static index during idle time so Cmd+K feels faster. */
export function SearchIndexPrefetch({ indexUrl }: { indexUrl: string }) {
  useEffect(() => {
    const prefetch = () => {
      void fetch(indexUrl, {
        credentials: "same-origin",
        mode: "cors",
      }).catch(() => undefined);
    };

    if ("requestIdleCallback" in globalThis) {
      const id = globalThis.requestIdleCallback(prefetch);
      return () => {
        globalThis.cancelIdleCallback(id);
      };
    }

    const timer = setTimeout(prefetch, 2000);
    return () => {
      clearTimeout(timer);
    };
  }, [indexUrl]);

  return null;
}
