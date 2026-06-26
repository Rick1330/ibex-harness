import Link from "next/link";

import { RoadmapProgress } from "@/components/roadmap/roadmap-progress";

type PhaseCardProps = Readonly<{
  slug: string;
  title: string;
  description?: string;
  subtitle?: string;
  completed: number;
  total: number;
  milestonesPending?: boolean;
}>;

export function PhaseCard({
  slug,
  title,
  description,
  subtitle,
  completed,
  total,
  milestonesPending = false,
}: PhaseCardProps) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <Link
      href={`/roadmap/${slug}`}
      className="group flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:bg-muted/20"
    >
      <div className="mb-3">
        <h2 className="text-base font-semibold text-foreground group-hover:underline">
          {title}
        </h2>
      </div>

      {description ? (
        <p className="mb-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
      {subtitle ? (
        <p className="mb-4 text-xs text-muted-foreground">{subtitle}</p>
      ) : null}
      {!subtitle && description ? <div className="mb-4" /> : null}

      {milestonesPending ? (
        <p className="mt-auto text-xs text-muted-foreground">
          Goals defined — milestones coming soon
        </p>
      ) : (
        <div className="mt-auto space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Milestones</span>
            <span className="tabular-nums">
              {completed}/{total}
            </span>
          </div>
          <RoadmapProgress value={pct} />
        </div>
      )}
    </Link>
  );
}
