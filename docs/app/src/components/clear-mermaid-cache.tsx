"use client";

import { useEffect } from "react";

/** Remove stale Mermaid keys from localStorage on load (never caches SVG ourselves). */
export function ClearMermaidCache() {
  useEffect(() => {
    try {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith("mermaid-")) {
          localStorage.removeItem(key);
        }
      }
    } catch {
      // localStorage may be unavailable
    }
  }, []);

  return null;
}
