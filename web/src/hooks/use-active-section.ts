"use client";

import { useEffect, useState } from "react";

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

    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const intersecting = new Set<Element>();

    const pickActive = () => {
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && intersecting.has(el)) {
          setActive(id);
          return;
        }
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            intersecting.add(entry.target);
          } else {
            intersecting.delete(entry.target);
          }
        }
        pickActive();
      },
      { rootMargin, threshold: [0, 0.25, 0.5] },
    );

    for (const el of elements) observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [ids, rootMargin]);

  return active;
}
