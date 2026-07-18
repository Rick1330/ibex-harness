"use client";

import { useMemo } from "react";

import { useActiveSection } from "@/hooks/use-active-section";
import { cn } from "@/lib/cn";
import type { ChangelogNavGroup } from "@/lib/changelog/grouping";

type ChangelogYearNavProps = Readonly<{
  groups: ReadonlyArray<ChangelogNavGroup>;
}>;

function QuarterLink({
  anchor,
  label,
  count,
  active,
}: Readonly<{
  anchor: string;
  label: string;
  count: number;
  active: boolean;
}>) {
  return (
    <li>
      <a
        href={`#${anchor}`}
        className={cn(
          "changelog-nav-quarter",
          active && "changelog-nav-quarter-active",
        )}
      >
        <span>{label}</span>
        <span className="changelog-nav-count">{count}</span>
      </a>
    </li>
  );
}

/** Sticky year → quarter rail (DESIGN_GUIDE §15.1). */
export function ChangelogYearNav({ groups }: ChangelogYearNavProps) {
  const ids = useMemo(
    () => groups.flatMap((group) => group.quarters.map((q) => q.anchor)),
    [groups],
  );
  const active = useActiveSection(ids);

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
                <QuarterLink
                  key={quarter.anchor}
                  anchor={quarter.anchor}
                  label={quarter.label}
                  count={quarter.count}
                  active={active === quarter.anchor}
                />
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </nav>
  );
}
