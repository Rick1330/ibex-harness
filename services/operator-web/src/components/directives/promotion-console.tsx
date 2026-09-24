"use client"

import * as React from "react"
import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type {
  ActionLedgerEntry,
  BlastRadius,
  RolloutState,
  RolloutStrategy,
  RevokeResult,
} from "@/lib/directives/types"
import { CONTROLLED_ACTIONS_ENABLED } from "@/lib/directives/types"
import { cn } from "@/lib/utils"

export function PromotionConsole({
  targetVersion,
  baselineVersion,
  blockedReason,
  blast,
  rollout,
  onLedger,
  onRolloutChange,
}: {
  targetVersion: number
  baselineVersion: number
  blockedReason: string | null
  blast: BlastRadius
  rollout: RolloutState | null
  onLedger: (entry: ActionLedgerEntry) => void
  onRolloutChange: (next: RolloutState | null) => void
}) {
  const { openStepUp } = useAuth()
  const [strategy, setStrategy] = React.useState<RolloutStrategy>(
    blast.strategy,
  )
  const [revokeReason, setRevokeReason] = React.useState("")
  const [approverId, setApproverId] = React.useState("")
  const [revokeResult, setRevokeResult] = React.useState<RevokeResult | null>(
    null,
  )
  const promoteKeys = React.useRef(new Set<string>())

  const canPromote = CONTROLLED_ACTIONS_ENABLED && !blockedReason

  const promote = () => {
    if (!CONTROLLED_ACTIONS_ENABLED) {
      toast.error("Controlled actions disabled — fail closed")
      return
    }
    if (blockedReason) {
      toast.error("409 REGRESSION_NOT_PASSED", { description: blockedReason })
      return
    }
    openStepUp((stepUpToken) => {
      const key = `promote:v${baselineVersion}->v${targetVersion}:${strategy}`
      if (promoteKeys.current.has(key)) {
        toast.message("Idempotent no-op", {
          description: "Same promote already recorded — one ledger entry.",
        })
        return
      }
      promoteKeys.current.add(key)
      onLedger({
        id: `led_${Date.now()}`,
        at: new Date().toISOString(),
        actor: "operator@acme.com",
        kind: "promote",
        summary: `promote v${baselineVersion}→v${targetVersion} ${strategy}`,
        before_version: baselineVersion,
        after_version: targetVersion,
        idempotency_key: key,
        reason: `X-IBEX-Step-Up · ${stepUpToken.slice(0, 18)}… · strategy ${strategy}`,
      })
      toast.success(`Promoted v${targetVersion}`, {
        description: `Strategy ${strategy}. Blast: ${blast.sessions_affected} sessions.`,
      })
    })
  }

  const pause = () => {
    if (!rollout || !CONTROLLED_ACTIONS_ENABLED) return
    const next = {
      ...rollout,
      paused: !rollout.paused,
      stage: !rollout.paused ? ("paused" as const) : rollout.stage,
    }
    onRolloutChange(next)
    onLedger({
      id: `led_${Date.now()}`,
      at: new Date().toISOString(),
      actor: "operator@acme.com",
      kind: next.paused ? "pause_rollout" : "resume_rollout",
      summary: next.paused
        ? `pause rollout at ${rollout.percentage}%`
        : `resume rollout at ${rollout.percentage}%`,
      before_version: rollout.baseline_version,
      after_version: rollout.target_version,
      idempotency_key: `pause:${rollout.target_version}:${Date.now()}`,
    })
  }

  const simulateAbort = () => {
    if (!rollout || !CONTROLLED_ACTIONS_ENABLED) return
    const aborted: RolloutState = {
      ...rollout,
      percentage: 0,
      stage: "aborted",
      paused: true,
      auto_abort: {
        at: new Date().toISOString(),
        reason: "latency guardrail breached",
        rolled_back_to: rollout.baseline_version,
        at_percentage: rollout.percentage,
      },
      quality_signal: "aborted — guardrail breach",
    }
    onRolloutChange(aborted)
    onLedger({
      id: `led_${Date.now()}`,
      at: new Date().toISOString(),
      actor: "system",
      kind: "auto_rollback",
      summary: `auto-rollback to v${rollout.baseline_version} at ${rollout.percentage}%`,
      before_version: rollout.target_version,
      after_version: rollout.baseline_version,
      idempotency_key: `abort:${rollout.target_version}:${Date.now()}`,
      reason: "latency guardrail breached",
    })
    toast.message("Automated abort", {
      description: `Rolled back to v${rollout.baseline_version} at ${rollout.percentage}%`,
    })
  }

  const revoke = () => {
    if (!CONTROLLED_ACTIONS_ENABLED) {
      toast.error("Controlled actions disabled — fail closed")
      return
    }
    if (!revokeReason.trim() || !approverId.trim()) {
      toast.error("Revoke requires reason and approver_id")
      return
    }
    openStepUp((stepUpToken) => {
      const result: RevokeResult = {
        affected_sessions: blast.sessions_affected,
        sessions_transitioned_to_fallback: blast.sessions_affected,
        fallback_version: baselineVersion,
      }
      setRevokeResult(result)
      onLedger({
        id: `led_${Date.now()}`,
        at: new Date().toISOString(),
        actor: "operator@acme.com",
        kind: "revoke",
        summary: `revoke v${targetVersion} step-up+approver`,
        before_version: targetVersion,
        after_version: baselineVersion,
        idempotency_key: `revoke:v${targetVersion}`,
        reason: `${revokeReason} · X-IBEX-Step-Up ${stepUpToken.slice(0, 18)}…`,
      })
      toast.success("Emergency revoke complete", {
        description: `${result.sessions_transitioned_to_fallback} sessions → fallback v${result.fallback_version}`,
      })
    })
  }

  return (
    <div className="space-y-3">
      <Card className={panelClass}>
        <CardHeader className="gap-1 border-b px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Promotion console — v{targetVersion}
          </CardTitle>
          <p className="text-[13px] text-muted-foreground">
            Preview → step-up → promote. Blocking conditions shown before click
            — never a silent 409.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3 text-[13px] leading-5">
          {blockedReason && (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
              Promote disabled: {blockedReason}
            </p>
          )}

          <div className="rounded-md border px-3 py-2 font-mono text-[13px]">
            <div className="mb-1 text-muted-foreground">Blast radius</div>
            <div>
              {blast.agents_affected} agent ·{" "}
              {blast.sessions_affected.toLocaleString()} sessions
            </div>
            <div className="mt-1 text-muted-foreground">
              MFA required: {String(blast.mfa_required)} · dual approval:{" "}
              {String(blast.dual_approval_required)}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <label htmlFor="rollout-strategy" className="text-[13px] text-muted-foreground">
                Rollout strategy
              </label>
              <Select
                name="rollout-strategy"
                value={strategy}
                onValueChange={(v) => setStrategy(v as RolloutStrategy)}
              >
                <SelectTrigger
                  size="sm"
                  className="w-full max-w-[180px] sm:w-[180px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="immediate">immediate</SelectItem>
                  <SelectItem value="new_sessions_only">
                    new_sessions_only
                  </SelectItem>
                  <SelectItem value="gradual">gradual</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <span className="text-[13px] text-muted-foreground">
                Step-up
              </span>
              <p className="max-w-[160px] text-[11px] text-muted-foreground">
                DirectivePromote opens in-context TOTP (X-IBEX-Step-Up) — not a
                page redirect.
              </p>
            </div>
            <Button size="sm" disabled={!canPromote} onClick={promote}>
              Promote ▾
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!CONTROLLED_ACTIONS_ENABLED}
              onClick={() => {
                onLedger({
                  id: `led_${Date.now()}`,
                  at: new Date().toISOString(),
                  actor: "operator@acme.com",
                  kind: "submit_review",
                  summary: `submit v${targetVersion} for review`,
                  before_version: null,
                  after_version: targetVersion,
                  idempotency_key: `review:v${targetVersion}`,
                })
                toast.success("Submitted for review")
              }}
            >
              Submit for Review
            </Button>
          </div>
        </CardContent>
      </Card>

      {rollout && (
        <Card className={panelClass}>
          <CardHeader className="gap-2 border-b px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-[13px] font-medium">
                Rollout: v{rollout.target_version}
              </CardTitle>
              <Button size="sm" variant="outline" onClick={pause}>
                {rollout.paused ? "Resume" : "Pause"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-[13px]"
                onClick={simulateAbort}
              >
                Simulate guardrail abort
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 px-4 py-3 text-[13px] leading-5">
            {rollout.auto_abort && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
                Rolled back to v{rollout.auto_abort.rolled_back_to}{" "}
                automatically: {rollout.auto_abort.reason} at{" "}
                {rollout.auto_abort.at_percentage}% rollout
              </p>
            )}
            <div className="flex flex-wrap gap-2 font-mono text-[13px]">
              {rollout.stages.map((s) => (
                <span
                  key={s.id}
                  className={cn(
                    "rounded border px-2 py-0.5",
                    s.done &&
                      "border-emerald-600/40 text-emerald-800 dark:text-emerald-300",
                    s.current && !s.done && "border-foreground/50 font-medium",
                    !s.done && !s.current && "text-muted-foreground",
                  )}
                >
                  {s.done ? "✓ " : s.current ? "→ " : ""}
                  {s.label}
                  {s.current && !rollout.paused ? (
                    <span className="ml-1 text-muted-foreground">
                      ▓▓▓▓░░░░░░
                    </span>
                  ) : null}
                </span>
              ))}
            </div>
            <p className="font-mono text-[13px] text-muted-foreground">
              Bake window: {rollout.bake_remaining}
            </p>
            <p className="font-mono text-[13px] text-muted-foreground">
              Quality signal: {rollout.quality_signal}
            </p>
            <p className="rounded-md border bg-muted/30 px-3 py-2 text-[13px] leading-5 text-muted-foreground">
              Sticky-hash: same{" "}
              <span className="font-mono text-foreground">
                (agent_id, session_id)
              </span>{" "}
              always resolves to the same version within this rollout window —
              not random mid-session flips.
            </p>
          </CardContent>
        </Card>
      )}

      <Card className={cn(panelClass, "border-destructive/40")}>
        <CardHeader className="gap-1 border-b border-destructive/30 bg-destructive/5 px-4 py-3">
          <CardTitle className="text-[13px] font-medium text-destructive">
            Emergency revoke
          </CardTitle>
          <p className="text-[13px] text-muted-foreground">
            Distinct from routine rollback — switches active sessions to
            fallback immediately. Reason + approver_id required inline.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
              placeholder="Reason (required)"
              className="h-9 text-[13px]"
            />
            <Input
              value={approverId}
              onChange={(e) => setApproverId(e.target.value)}
              placeholder="approver_id (2-person)"
              className="h-9 font-mono text-[13px]"
            />
          </div>
          <Button
            size="sm"
            variant="destructive"
            disabled={!CONTROLLED_ACTIONS_ENABLED}
            onClick={revoke}
          >
            Revoke — MFA required
          </Button>
          {revokeResult && (
            <p className="font-mono text-[13px] text-muted-foreground">
              affected_sessions={revokeResult.affected_sessions} ·
              sessions_transitioned_to_fallback=
              {revokeResult.sessions_transitioned_to_fallback} · fallback v
              {revokeResult.fallback_version}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
