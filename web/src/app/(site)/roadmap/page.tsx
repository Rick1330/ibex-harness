import type { Metadata } from "next";

import {
  RoadmapCriticalPathSection,
  RoadmapHubFooter,
  RoadmapPhasesSection,
  RoadmapProgressSection,
  RoadmapRecentSection,
  RoadmapReferenceSection,
} from "@/components/roadmap/roadmap-hub-sections";
import { PhaseTimeline } from "@/components/roadmap/phase-timeline";
import {
  getOverallRoadmapStats,
  getPhaseCards,
  getRecentCompletedMilestones,
} from "@/lib/roadmap-hub";

export const metadata: Metadata = {
  title: "Development Roadmap",
  description:
    "Track IBEX Harness from foundation through core platform, docs site, provider adapters, and beyond.",
};

export default function RoadmapHubPage() {
  const { total, completed, progressPct } = getOverallRoadmapStats();
  const phases = getPhaseCards();
  const recent = getRecentCompletedMilestones(5);

  return (
    <main className="container mx-auto max-w-5xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <header className="mb-12">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Roadmap
        </p>
        <h1 className="mb-3 text-3xl font-bold tracking-tight text-foreground md:text-4xl">
          Development Roadmap
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-muted-foreground">
          Supplementary implementation guide for IBEX Harness — phases, milestones,
          and day-to-day delivery specs. Drill into any phase for full milestone
          detail.
        </p>
      </header>

      <RoadmapReferenceSection />
      <RoadmapProgressSection
        completed={completed}
        total={total}
        progressPct={progressPct}
      />

      <section className="mb-12">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Phase timeline
        </h2>
        <PhaseTimeline phases={phases} />
      </section>

      <RoadmapCriticalPathSection />
      <RoadmapRecentSection recent={recent} />
      <RoadmapPhasesSection phases={phases} />
      <RoadmapHubFooter />
    </main>
  );
}
