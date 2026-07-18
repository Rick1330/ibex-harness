"use client";

import { useEffect, useState } from "react";

/**
 * Track which section id is nearest the top of the viewport via IntersectionObserver.
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

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) =>
              a.boundingClientRect.top - b.boundingClientRect.top,
          );
        const top = visible[0]?.target;
        if (top?.id) setActive(top.id);
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
