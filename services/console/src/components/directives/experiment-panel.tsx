"use client"

import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ActionLedgerEntry, ExperimentState } from "@/lib/directives/types"
import { CONTROLLED_ACTIONS_ENABLED } from "@/lib/directives/types"
import { cn } from "@/lib/utils"

export function ExperimentPanel({
  experiment,
  onChange,
  onLedger,
}: {
  experiment: ExperimentState
  onChange: (next: ExperimentState) => void
  onLedger: (entry: ActionLedgerEntry) => void
}) {
  const kill = () => {
    if (!CONTROLLED_ACTIONS_ENABLED) {
      toast.error("Controlled actions disabled — fail closed")
      return
    }
    if (experiment.status === "killed") {
      toast.message("Already killed")
      return
    }
    onChange({ ...experiment, status: "killed" })
    onLedger({
      id: `led_${Date.now()}`,
      at: new Date().toISOString(),
      actor: "operator@acme.com",
      kind: "kill_experiment",
      summary: `kill experiment ${experiment.experiment_id}`,
      before_version: null,
      after_version: null,
      idempotency_key: `kill:${experiment.experiment_id}`,
      reason: "operator kill switch",
    })
    toast.success("Experiment killed", {
      description: "Distinct from rollout Pause — all arms stopped.",
    })
  }

  return (
    <Card
      className={cn(
        panelClass,
        "border-sky-600/30",
        experiment.status === "killed" && "opacity-80",
      )}
    >
      <CardHeader className="gap-2 border-b border-sky-600/20 bg-sky-500/5 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-[13px] font-medium">
            Experiment — {experiment.name}
          </CardTitle>
          <span className="font-mono text-[13px] text-muted-foreground">
            {experiment.status}
          </span>
          <Button
            size="sm"
            variant="destructive"
            className="ml-auto"
            disabled={
              !CONTROLLED_ACTIONS_ENABLED || experiment.status === "killed"
            }
            onClick={kill}
          >
            Kill this experiment now
          </Button>
        </div>
        <p className="text-[13px] text-muted-foreground">
          Kill switch is visually distinct from rollout Pause — shared guardrail
          machinery, different operator intent.
        </p>
      </CardHeader>
      <CardContent className="space-y-2 px-4 py-3 font-mono text-[13px] leading-5">
        <div>
          assigned arm:{" "}
          <span className="text-foreground">{experiment.assigned_arm}</span>
          {experiment.holdback ? " · holdback" : ""}
        </div>
        <div className="text-muted-foreground">
          exposure @ {experiment.exposure_at} · guardrails:{" "}
          {experiment.guardrail_summary}
        </div>
        <ul className="mt-2 space-y-1">
          {experiment.arms.map((a) => (
            <li key={a.arm_id} className="flex justify-between gap-2">
              <span
                className={cn(
                  a.arm_id === experiment.assigned_arm &&
                    "font-medium text-foreground",
                )}
              >
                {a.label}
              </span>
              <span className="text-muted-foreground">{a.exposure_pct}%</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
