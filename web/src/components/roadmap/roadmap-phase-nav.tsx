"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import type { MilestoneStatus } from "@/lib/roadmap-types";

export type RoadmapNavPhase = Readonly<{
  anchor: string;
  phaseIndex: string;
  shortTitle: string;
  status?: MilestoneStatus;
}>;

type RoadmapPhaseNavProps = Readonly<{
  phases: ReadonlyArray<RoadmapNavPhase>;
}>;

function statusLabel(status?: MilestoneStatus): string {
  if (status === "completed") return "Shipped";
  if (status === "in-progress") return "In progress";
  return "Planned";
}

/** Sticky phase rail — DESIGN_GUIDE §17. */
export function RoadmapPhaseNav({ phases }: RoadmapPhaseNavProps) {
  const [active, setActive] = useState(phases[0]?.anchor ?? null);

  useEffect(() => {
    const ids = phases.map((p) => p.anchor);
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        const top = visible[0]?.target;
        if (top?.id) setActive(top.id);
      },
      { rootMargin: "-18% 0px -55% 0px", threshold: [0, 0.2, 0.5] },
    );

    for (const el of elements) observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [phases]);

  if (phases.length === 0) return null;

  return (
    <nav className="roadmap-nav" aria-label="Roadmap phases">
      <p className="roadmap-nav-label">Phases</p>
      <ul className="roadmap-nav-list">
        {phases.map((phase) => (
          <li key={phase.anchor}>
            <a
              href={`#${phase.anchor}`}
              className={cn(
                "roadmap-nav-item",
                active === phase.anchor && "roadmap-nav-item-active",
              )}
            >
              <span
                className={cn(
                  "roadmap-nav-dot",
                  phase.status === "completed" && "roadmap-dot-shipped",
                  phase.status === "in-progress" && "roadmap-dot-progress",
                  (!phase.status || phase.status === "planned") &&
                    "roadmap-dot-planned",
                )}
                aria-hidden
              />
              <span className="roadmap-nav-text">
                <span className="roadmap-nav-index">
                  Phase {phase.phaseIndex}
                </span>
                <span className="roadmap-nav-title">{phase.shortTitle}</span>
                <span className="roadmap-nav-status">
                  {statusLabel(phase.status)}
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
