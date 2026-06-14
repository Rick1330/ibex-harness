import Link from "next/link";
import type { ReactNode } from "react";

import { MilestoneStatusBadge } from "@/components/roadmap/milestone-status-badge";
import type { MilestoneStatus } from "@/lib/roadmap-types";

type MilestoneMetaStripProps = {
  status?: MilestoneStatus;
  milestoneId?: string;
  goal?: string;
  phase?: string;
  estimatedEffort?: string;
  completedDate?: string;
};

function GoalValue({ goal }: { goal: string }) {
  const pathMatch = goal.match(/^\[(.+?)\]\((\/[^)]+)\)$/);
  if (pathMatch) {
    return (
      <Link
        href={pathMatch[2]}
        className="text-foreground underline-offset-2 hover:underline"
      >
        {pathMatch[1]}
      </Link>
    );
  }

  const mdLink = goal.match(/\[([^\]]+)\]\(([^)]+)\)/);
  if (mdLink) {
    let href = mdLink[2];
    if (href.endsWith(".md") || href.includes(".md#")) {
      href = href.replace(/\.md(?=#|$)/, "").replace(/^\.\.\//, "");
      if (!href.startsWith("/")) {
        href = `/roadmap/${href}`;
      }
    }
    if (href.startsWith("/")) {
      return (
        <Link
          href={href}
          className="text-foreground underline-offset-2 hover:underline"
        >
          {mdLink[1]}
        </Link>
      );
    }
  }

  return <span>{goal.replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")}</span>;
}

export function MilestoneMetaStrip({
  status,
  milestoneId,
  goal,
  phase,
  estimatedEffort,
  completedDate,
}: MilestoneMetaStripProps) {
  const items: { label: string; value: ReactNode }[] = [];

  if (status) {
    items.push({
      label: "Status",
      value: <MilestoneStatusBadge status={status} />,
    });
  }
  if (milestoneId) {
    items.push({ label: "ID", value: <span className="font-mono">{milestoneId}</span> });
  }
  if (completedDate) {
    items.push({ label: "Completed", value: completedDate });
  }
  if (goal) {
    items.push({ label: "Goal", value: <GoalValue goal={goal} /> });
  }
  if (phase) {
    items.push({ label: "Phase", value: phase });
  }
  if (estimatedEffort) {
    items.push({ label: "Effort", value: estimatedEffort });
  }

  if (items.length === 0) return null;

  return (
    <dl className="mb-8 grid gap-3 rounded-lg border border-border bg-muted/10 p-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map(({ label, value }) => (
        <div key={label} className="min-w-0">
          <dt className="mb-0.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </dt>
          <dd className="text-sm text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
