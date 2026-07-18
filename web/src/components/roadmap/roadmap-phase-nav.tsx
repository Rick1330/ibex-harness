"use client";

import { useMemo } from "react";

import { useActiveSection } from "@/hooks/use-active-section";
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

function statusDotClass(status?: MilestoneStatus): string {
  if (status === "completed") return "roadmap-dot-shipped";
  if (status === "in-progress") return "roadmap-dot-progress";
  return "roadmap-dot-planned";
}

function PhaseNavItem({
  phase,
  active,
}: Readonly<{ phase: RoadmapNavPhase; active: boolean }>) {
  return (
    <li>
      <a
        href={`#${phase.anchor}`}
        className={cn(
          "roadmap-nav-item",
          active && "roadmap-nav-item-active",
        )}
      >
        <span
          className={cn("roadmap-nav-dot", statusDotClass(phase.status))}
          aria-hidden
        />
        <span className="roadmap-nav-text">
          <span className="roadmap-nav-index">Phase {phase.phaseIndex}</span>
          <span className="roadmap-nav-title">{phase.shortTitle}</span>
          <span className="roadmap-nav-status">
            {statusLabel(phase.status)}
          </span>
        </span>
      </a>
    </li>
  );
}

/** Sticky phase rail — DESIGN_GUIDE §17. */
export function RoadmapPhaseNav({ phases }: RoadmapPhaseNavProps) {
  const ids = useMemo(() => phases.map((p) => p.anchor), [phases]);
  const active = useActiveSection(ids, "-18% 0px -55% 0px");

  if (phases.length === 0) return null;

  return (
    <nav className="roadmap-nav" aria-label="Roadmap phases">
      <p className="roadmap-nav-label">Phases</p>
      <ul className="roadmap-nav-list">
        {phases.map((phase) => (
          <PhaseNavItem
            key={phase.anchor}
            phase={phase}
            active={active === phase.anchor}
          />
        ))}
      </ul>
    </nav>
  );
}
