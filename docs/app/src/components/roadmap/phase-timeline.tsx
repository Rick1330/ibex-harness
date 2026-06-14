import Link from "next/link";

type PhaseTimelineProps = {
  phases: {
    slug: string;
    title: string;
    milestonesPending?: boolean;
  }[];
};

export function PhaseTimeline({ phases }: PhaseTimelineProps) {
  return (
    <ol className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-stretch">
      {phases.map((phase, index) => (
        <li key={phase.slug} className="flex min-w-0 flex-1 sm:min-w-[8rem] sm:max-w-[10rem]">
          <Link
            href={`/roadmap/${phase.slug}`}
            className="group flex w-full flex-col rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/20"
          >
            <span className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Phase {index}
            </span>
            <span className="mb-2 line-clamp-2 text-xs font-medium leading-snug text-foreground group-hover:underline">
              {phase.title.replace(/^Phase \d+(?:\.\d+)?:\s*/i, "")}
            </span>
            {phase.milestonesPending ? (
              <span className="mt-auto text-[10px] text-muted-foreground">Goals only</span>
            ) : null}
          </Link>
        </li>
      ))}
    </ol>
  );
}
