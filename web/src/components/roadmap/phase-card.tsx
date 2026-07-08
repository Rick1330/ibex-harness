import Link from "next/link";

import { PhaseCardMilestones } from "@/components/roadmap/phase-card-milestones";

type PhaseCardProps = Readonly<{
  slug: string;
  title: string;
  description?: string;
  subtitle?: string;
  status?: "completed" | "in-progress" | "planned";
  completed: number;
  total: number;
  milestonesPending?: boolean;
}>;

function phaseProgressPercent(
  completed: number,
  total: number,
  status?: PhaseCardProps["status"],
): number {
  if (total > 0) {
    return Math.round((completed / total) * 100);
  }
  return status === "completed" ? 100 : 0;
}

export function PhaseCard({
  slug,
  title,
  description,
  subtitle,
  status,
  completed,
  total,
  milestonesPending = false,
}: PhaseCardProps) {
  const showCompleteLabel = total === 0 && status === "completed";
  const pct = phaseProgressPercent(completed, total, status);

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

      <PhaseCardMilestones
        milestonesPending={milestonesPending}
        showCompleteLabel={showCompleteLabel}
        completed={completed}
        total={total}
        pct={pct}
      />
    </Link>
  );
}
