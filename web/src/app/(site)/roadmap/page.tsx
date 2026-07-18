import type { Metadata } from "next";

import { RoadmapHubView } from "@/components/roadmap/roadmap-hub-view";
import {
  getOverallRoadmapStats,
  getPhaseTimeline,
  getRecentCompletedMilestones,
} from "@/lib/roadmap-hub";

export const metadata: Metadata = {
  title: "Roadmap",
  description:
    "IBEX Harness development roadmap — phases, milestones, and what ships next.",
};

export default function RoadmapHubPage() {
  const { total, completed, progressPct } = getOverallRoadmapStats();
  const phases = getPhaseTimeline();
  const recent = getRecentCompletedMilestones(5);

  return (
    <main className="roadmap-page">
      <RoadmapHubView
        phases={phases}
        recent={recent}
        completed={completed}
        total={total}
        progressPct={progressPct}
      />
    </main>
  );
}
