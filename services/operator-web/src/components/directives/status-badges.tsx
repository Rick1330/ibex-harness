"use client"

import { Badge } from "@/components/ui/badge"
import type {
  BehaviorAssessment,
  DirectiveLifecycle,
  RegressionStatus,
  RolloutStage,
} from "@/lib/directives/types"
import { cn } from "@/lib/utils"

const lifeTone: Record<DirectiveLifecycle, string> = {
  draft: "border-muted-foreground/40 text-muted-foreground",
  review: "border-amber-600/40 text-amber-900 dark:text-amber-200",
  active: "border-emerald-600/40 text-emerald-800 dark:text-emerald-300",
  deprecated: "border-muted-foreground/30 text-muted-foreground",
  revoked: "border-destructive/40 text-destructive",
}

const regTone: Record<RegressionStatus, string> = {
  passed: "border-emerald-600/40 text-emerald-800 dark:text-emerald-300",
  failed: "border-destructive/40 text-destructive",
  critical_fail: "border-destructive/50 text-destructive",
  pending: "border-amber-600/40 text-amber-900 dark:text-amber-200",
  not_run: "border-muted-foreground/30 text-muted-foreground",
}

const assessTone: Record<BehaviorAssessment, string> = {
  improvement: "border-emerald-600/40 text-emerald-800 dark:text-emerald-300",
  regression: "border-destructive/40 text-destructive",
  neutral: "border-muted-foreground/40 text-muted-foreground",
}

export function LifecycleBadge({ status }: { status: DirectiveLifecycle }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", lifeTone[status])}
    >
      {status}
    </Badge>
  )
}

export function RegressionBadge({
  status,
  passed,
  total,
}: {
  status: RegressionStatus
  passed?: number
  total?: number
}) {
  const label =
    passed != null && total != null && status !== "not_run"
      ? `${status} ${passed}/${total}`
      : status
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", regTone[status])}
    >
      {label}
    </Badge>
  )
}

export function AssessmentBadge({
  assessment,
}: {
  assessment: BehaviorAssessment
}) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", assessTone[assessment])}
    >
      {assessment}
    </Badge>
  )
}

export function RolloutStageChip({
  stage,
  percentage,
}: {
  stage: RolloutStage
  percentage: number
}) {
  return (
    <Badge variant="outline" className="font-mono text-[13px]">
      rollout {percentage}% · {stage.replace("pct_", "")}
    </Badge>
  )
}
