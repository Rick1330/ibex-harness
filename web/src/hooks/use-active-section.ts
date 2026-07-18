"use client";

import { useEffect, useState } from "react";

function syncIntersecting(
  intersecting: Set<Element>,
  entries: ReadonlyArray<IntersectionObserverEntry>,
): void {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      intersecting.add(entry.target);
    } else {
      intersecting.delete(entry.target);
    }
  }
}

function firstIntersectingId(
  ids: ReadonlyArray<string>,
  intersecting: Set<Element>,
): string | null {
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el !== null && intersecting.has(el)) {
      return id;
    }
  }
  return null;
}

function observeActiveSection(
  ids: ReadonlyArray<string>,
  rootMargin: string,
  onActive: (id: string) => void,
): () => void {
  const elements = ids
    .map((id) => document.getElementById(id))
    .filter((el): el is HTMLElement => el !== null);
  if (elements.length === 0) {
    return () => {};
  }

  const intersecting = new Set<Element>();
  const observer = new IntersectionObserver(
    (entries) => {
      syncIntersecting(intersecting, entries);
      const next = firstIntersectingId(ids, intersecting);
      if (next !== null) {
        onActive(next);
      }
    },
    { rootMargin, threshold: [0, 0.25, 0.5] },
  );

  for (const el of elements) observer.observe(el);
  return () => {
    observer.disconnect();
  };
}

/**
 * Track which section id is nearest the top of the viewport via IntersectionObserver.
 * Keeps a persistent set of currently intersecting targets so leaving one section
 * still selects another visible section (ordered by `ids`).
 */
export function useActiveSection(
  ids: ReadonlyArray<string>,
  rootMargin = "-20% 0px -55% 0px",
): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    if (ids.length === 0) return;
    return observeActiveSection(ids, rootMargin, setActive);
  }, [ids, rootMargin]);

  return active;
}
