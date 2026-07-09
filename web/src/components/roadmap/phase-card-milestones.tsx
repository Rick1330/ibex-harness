import { RoadmapProgress } from "@/components/roadmap/roadmap-progress";

type PhaseCardMilestonesProps = Readonly<{
  milestonesPending: boolean;
  showCompleteLabel: boolean;
  completed: number;
  total: number;
  pct: number;
}>;

export function PhaseCardMilestones({
  milestonesPending,
  showCompleteLabel,
  completed,
  total,
  pct,
}: PhaseCardMilestonesProps) {
  if (milestonesPending) {
    return (
      <p className="mt-auto text-xs text-muted-foreground">
        Goals defined — milestones coming soon
      </p>
    );
  }

  return (
    <div className="mt-auto space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Milestones</span>
        <span className="tabular-nums">
          {showCompleteLabel ? "Complete" : `${completed}/${total}`}
        </span>
      </div>
      <RoadmapProgress value={pct} />
    </div>
  );
}
