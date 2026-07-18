import Link from "next/link";

import { cn } from "@/lib/cn";
import type { MilestoneStatus } from "@/lib/roadmap-types";

export type RoadmapTimelinePhase = Readonly<{
  slug: string;
  anchor: string;
  phaseIndex: string;
  shortTitle: string;
  title: string;
  description?: string;
  status?: MilestoneStatus;
  completed: number;
  total: number;
  milestonesPending?: boolean;
  bullets: ReadonlyArray<{
    title: string;
    url: string;
    status: MilestoneStatus;
  }>;
}>;

type RoadmapTimelineProps = Readonly<{
  phases: ReadonlyArray<RoadmapTimelinePhase>;
}>;

function statusLabel(status?: MilestoneStatus): string {
  if (status === "completed") return "shipped";
  if (status === "in-progress") return "in progress";
  return "planned";
}

/** Vertical phase timeline — filled / half / hollow dots (DESIGN_GUIDE §17). */
export function RoadmapTimeline({ phases }: RoadmapTimelineProps) {
  return (
    <ol className="roadmap-timeline">
      {phases.map((phase, index) => {
        const isLast = index === phases.length - 1;
        return (
          <li
            key={phase.slug}
            id={phase.anchor}
            className="roadmap-timeline-item"
          >
            <div className="roadmap-timeline-gutter" aria-hidden>
              <span
                className={cn(
                  "roadmap-timeline-dot",
                  phase.status === "completed" && "roadmap-dot-shipped",
                  phase.status === "in-progress" && "roadmap-dot-progress",
                  (!phase.status || phase.status === "planned") &&
                    "roadmap-dot-planned",
                )}
              />
              {!isLast ? <span className="roadmap-timeline-line" /> : null}
            </div>

            <div className="roadmap-timeline-content">
              <header className="roadmap-timeline-header">
                <p className="roadmap-timeline-meta">
                  <span>Phase {phase.phaseIndex}</span>
                  <span aria-hidden>·</span>
                  <span
                    className={cn(
                      "roadmap-timeline-status",
                      phase.status === "completed" &&
                        "roadmap-timeline-status-shipped",
                      phase.status === "in-progress" &&
                        "roadmap-timeline-status-progress",
                    )}
                  >
                    {statusLabel(phase.status)}
                  </span>
                  {phase.total > 0 ? (
                    <>
                      <span aria-hidden>·</span>
                      <span className="tabular-nums">
                        {phase.completed}/{phase.total}
                      </span>
                    </>
                  ) : null}
                </p>
                <h2 className="roadmap-timeline-title">
                  <Link href={`/roadmap/${phase.slug}`}>
                    {phase.shortTitle}
                  </Link>
                </h2>
                {phase.description ? (
                  <p className="roadmap-timeline-desc">{phase.description}</p>
                ) : null}
              </header>

              {phase.bullets.length > 0 ? (
                <ul className="roadmap-timeline-bullets">
                  {phase.bullets.map((bullet) => (
                    <li key={bullet.url}>
                      <Link
                        href={bullet.url}
                        className={cn(
                          "roadmap-timeline-bullet",
                          bullet.status === "completed" &&
                            "roadmap-timeline-bullet-done",
                        )}
                      >
                        <span
                          className={cn(
                            "roadmap-bullet-mark",
                            bullet.status === "completed" &&
                              "roadmap-dot-shipped",
                            bullet.status === "in-progress" &&
                              "roadmap-dot-progress",
                            bullet.status === "planned" &&
                              "roadmap-dot-planned",
                          )}
                          aria-hidden
                        />
                        {bullet.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : phase.milestonesPending ? (
                <p className="roadmap-timeline-pending">
                  Goals defined — milestones coming soon
                </p>
              ) : null}

              <p className="roadmap-timeline-cta">
                <Link href={`/roadmap/${phase.slug}`}>
                  Open phase →
                </Link>
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
