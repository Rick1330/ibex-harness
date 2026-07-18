"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import type { ChangelogNavGroup } from "@/lib/changelog/grouping";

type ChangelogYearNavProps = Readonly<{
  groups: ReadonlyArray<ChangelogNavGroup>;
}>;

/** Sticky year → quarter rail (DESIGN_GUIDE §15.1). */
export function ChangelogYearNav({ groups }: ChangelogYearNavProps) {
  const [active, setActive] = useState<string | null>(
    groups[0]?.quarters[0]?.anchor ?? null,
  );

  useEffect(() => {
    const anchors = groups.flatMap((group) =>
      group.quarters.map((q) => q.anchor),
    );
    if (anchors.length === 0) return;

    const elements = anchors
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
      {
        rootMargin: "-20% 0px -55% 0px",
        threshold: [0, 0.25, 0.5],
      },
    );

    for (const el of elements) observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [groups]);

  if (groups.length === 0) return null;

  return (
    <nav className="changelog-nav" aria-label="Changelog years">
      <p className="changelog-nav-label">Years</p>
      <ul className="changelog-nav-list">
        {groups.map((group) => (
          <li key={group.year} className="changelog-nav-year">
            <span className="changelog-nav-year-label">{group.year}</span>
            <ul className="changelog-nav-quarters">
              {group.quarters.map((quarter) => (
                <li key={quarter.anchor}>
                  <a
                    href={`#${quarter.anchor}`}
                    className={cn(
                      "changelog-nav-quarter",
                      active === quarter.anchor &&
                        "changelog-nav-quarter-active",
                    )}
                  >
                    <span>{quarter.label}</span>
                    <span className="changelog-nav-count">{quarter.count}</span>
                  </a>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </nav>
  );
}
