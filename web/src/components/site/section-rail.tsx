"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

const RAIL_MARKS = [
  { id: "overview", label: "§01" },
  { id: "capabilities", label: "§02" },
  { id: "request-path", label: "§03" },
  { id: "local-stack", label: "§04" },
] as const;

/**
 * Landing-only § rail — thin editorial strip under the top bar.
 * Matches Lovable reference: vertical brand + § marks only.
 */
export function SectionRail() {
  const [active, setActive] = useState<string>("overview");

  useEffect(() => {
    const ids = RAIL_MARKS.map((mark) => mark.id);
    const nodes = ids
      .map((id) => document.getElementById(id))
      .filter((node): node is HTMLElement => node !== null);

    if (nodes.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length === 0) return;
        setActive(visible[0].target.id);
      },
      {
        rootMargin: "-56px 0px -45% 0px",
        threshold: [0.15, 0.35, 0.55],
      },
    );

    for (const node of nodes) observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <aside
      data-section-rail=""
      className="landing-section-rail sticky top-[var(--topbar-h)] z-30 flex h-[calc(100vh-var(--topbar-h))] w-14 shrink-0 flex-col border-r border-border py-7 max-sm:hidden md:w-16"
      aria-label="Section rail"
    >
      <p className="landing-rail-brand" aria-hidden>
        IBEX HARNESS · V0.1 · PHASE 1
      </p>
      <nav
        className="landing-rail-nav mt-auto flex flex-col gap-2.5 pb-4"
        aria-label="On this page"
      >
        {RAIL_MARKS.map((mark) => {
          const isActive = active === mark.id;
          return (
            <a
              key={mark.id}
              href={`#${mark.id}`}
              aria-current={isActive ? "location" : undefined}
              className={cn(
                "landing-rail-mark",
                isActive && "landing-rail-mark-active",
              )}
            >
              {mark.label}
            </a>
          );
        })}
      </nav>
    </aside>
  );
}
