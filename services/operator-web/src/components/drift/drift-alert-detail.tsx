"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { EvidenceTable } from "@/components/drift/evidence-table"
import { FingerprintHistory } from "@/components/drift/fingerprint-history"
import { CopyId } from "@/components/explore/copy-id"
import { StatusDot } from "@/components/list/status-dot"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  AGENT_POLICY_SUPPORT,
  FINGERPRINTS_SUPPORT,
} from "@/lib/drift/fixtures"
import {
  FEATURE_LABEL,
  STAGE_LABEL,
  TEST_LABEL,
  actionTakenLabel,
  severityTone,
  statusTone,
} from "@/lib/drift/labels"
import type {
  DriftActionStage,
  DriftAlertDetail,
  DriftAlertStatus,
} from "@/lib/drift/types"
import { cn } from "@/lib/utils"

export function DriftAlertDetailView({
  alert: initial,
}: {
  alert: DriftAlertDetail
}) {
  const [alert, setAlert] = React.useState(initial)
  const [notes, setNotes] = React.useState("")
  const [confirm, setConfirm] = React.useState<
    | null
    | "resolve"
    | "false_positive"
    | "reset_baseline"
    | "notify"
    | "auto_suspend"
  >(null)
  const [stage, setStage] = React.useState<DriftActionStage>(
    alert.drift_action_stage,
  )
  const policy = AGENT_POLICY_SUPPORT
  const shadowRemaining = Math.max(
    0,
    policy.shadow_days_required - policy.shadow_days_elapsed,
  )
  const shadowReady = policy.shadow_days_elapsed >= policy.shadow_days_required
  const alertWindowLabel = alert.window_end.slice(5, 10)

  const requireNotes = (kind: "resolve" | "false_positive") => {
    if (!notes.trim()) {
      toast.error("Notes required", {
        description:
          kind === "false_positive"
            ? "False-positive marks feed threshold calibration (≤2% FP/week/agent)."
            : "High-severity resolution needs a written rationale.",
      })
      return false
    }
    if (
      kind === "resolve" &&
      alert.severity === "high" &&
      notes.trim().length < 8
    ) {
      toast.error("Notes too short", {
        description:
          "High-severity resolve requires substantive resolution_notes.",
      })
      return false
    }
    return true
  }

  const acknowledge = () => {
    if (alert.status !== "open") {
      toast.message("Already past open", {
        description: "Acknowledge only moves open → acknowledged.",
      })
      return
    }
    setAlert((prev) => ({
      ...prev,
      status: "acknowledged",
      acknowledged_at: new Date().toISOString(),
      acknowledged_by: "operator@acme.com",
    }))
    toast.success("Acknowledged", {
      description: "Sets acknowledged_at / acknowledged_by — does not resolve.",
    })
  }

  const resolve = (asFp: boolean) => {
    const kind = asFp ? "false_positive" : "resolve"
    if (!requireNotes(kind)) return
    const next: DriftAlertStatus = asFp ? "false_positive" : "resolved"
    setAlert((prev) => ({
      ...prev,
      status: next,
      resolved_at: new Date().toISOString(),
      resolution_notes: notes.trim(),
    }))
    setConfirm(null)
    setNotes("")
    toast.success(asFp ? "Marked false positive" : "Resolved", {
      description: asFp
        ? "Recorded as calibration signal — not a silent dismiss."
        : "Webhook drift.resolved will fire when the write path ships.",
    })
  }

  const resetBaseline = () => {
    setConfirm(null)
    toast.success("Baseline reset queued", {
      description:
        "Today's fingerprint becomes is_baseline — future alerts compare against this window.",
    })
  }

  const promoteStage = (next: DriftActionStage) => {
    setStage(next)
    setConfirm(null)
    toast.success(`Action stage → ${STAGE_LABEL[next]}`, {
      description:
        next === "auto_suspend"
          ? "Enforcement reuses ValidateAgent AGENT_SUSPENDED — not a bespoke path."
          : "Org owner will receive webhook / email / Slack on high severity.",
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[18px] font-semibold tracking-tight">
              <Link
                href={`/dashboard/agents/${alert.agent_id}`}
                className="hover:underline"
              >
                {alert.agent_name}
              </Link>
            </h1>
            <StatusDot
              tone={severityTone(alert.severity)}
              label={alert.severity}
            />
            <StatusDot tone={statusTone(alert.status)} label={alert.status} />
            {alert.shadow_mode ? (
              <span className="rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground">
                Shadow mode — logging only
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
            <CopyId value={alert.alert_id} />
            <span>·</span>
            <span>
              stage{" "}
              <span className="text-foreground">{STAGE_LABEL[stage]}</span>
            </span>
            <span>·</span>
            <span>
              action{" "}
              <span className="font-mono text-foreground">
                {actionTakenLabel(alert.action_taken)}
              </span>
            </span>
            <span>·</span>
            <span>
              created{" "}
              <span className="font-mono text-foreground">
                {alert.created_at.replace("T", " ").slice(0, 16)}Z
              </span>
            </span>
            {alert.acknowledged_at ? (
              <>
                <span>·</span>
                <span>
                  ack{" "}
                  <span className="text-foreground">
                    {alert.acknowledged_by}
                  </span>
                </span>
              </>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <Link
              href={`/dashboard/explore?agent=${alert.agent_slug}&from=${encodeURIComponent(alert.window_start)}&to=${encodeURIComponent(alert.window_end)}`}
            >
              Contributing traces →
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link
              href={`/dashboard/directives?agent=${alert.agent_id}&regression=1&from_drift=${alert.alert_id}`}
            >
              Run regression from here →
            </Link>
          </Button>
        </div>
      </div>

      {alert.triggered_rollout_rollback &&
      alert.rollback_directive_version != null ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2.5 text-[12px]">
          <div className="font-medium text-foreground">
            Automatic rollout rollback (policy exception)
          </div>
          <p className="mt-0.5 text-muted-foreground">
            This alert triggered an automatic rollback of directive rollout v
            {alert.rollback_directive_version}. Gradual directive rollouts
            (4.5.C.3) roll back on drift{" "}
            <span className="text-foreground">
              regardless of the org&apos;s action-ladder stage
            </span>{" "}
            — including while suspension remains in shadow.
          </p>
          <Button asChild size="sm" variant="link" className="mt-1 h-auto px-0">
            <Link
              href={`/dashboard/directives?version=${alert.rollback_directive_version}`}
            >
              Open directive v{alert.rollback_directive_version} →
            </Link>
          </Button>
        </div>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Lane
          title="Which feature drifted"
          body={alert.feature_classes.map((f) => FEATURE_LABEL[f]).join(", ")}
        />
        <Lane
          title="How far from baseline"
          body={
            alert.evidence.find((e) => e.flagged)?.current_summary ??
            "See evidence table"
          }
        />
        <Lane
          title="Statistical test"
          body={
            alert.evidence
              .filter((e) => e.flagged)
              .map((e) => TEST_LABEL[e.test])
              .join(" · ") || "—"
          }
        />
        <Lane
          title="Action taken"
          body={`${actionTakenLabel(alert.action_taken)} · stage ${STAGE_LABEL[stage]}`}
        />
      </div>

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,22rem)]">
        <Card className={cn(panelClass, "min-w-0 overflow-hidden")}>
          <CardHeader className="border-b border-border/60 px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Per-feature evidence
            </CardTitle>
            <p className="text-[12px] text-muted-foreground">
              Persisted test_statistic and threshold_used shown separately —
              never a single drift score. Shape matches the test family.
            </p>
          </CardHeader>
          <CardContent className="min-w-0 overflow-x-auto px-0 py-0">
            <EvidenceTable evidence={alert.evidence} />
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-4">
          <Card className={panelClass}>
            <CardHeader className="border-b border-border/60 px-4 py-3">
              <CardTitle className="text-[13px] font-medium">
                Resolution
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 px-4 py-3">
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="resolution_notes (required for resolve / FP)"
                className="h-8 text-[13px]"
                aria-label="Resolution notes"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={alert.status !== "open"}
                  onClick={acknowledge}
                >
                  Acknowledge
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={
                    alert.status === "resolved" ||
                    alert.status === "false_positive"
                  }
                  onClick={() => setConfirm("resolve")}
                >
                  Resolve
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={
                    alert.status === "resolved" ||
                    alert.status === "false_positive"
                  }
                  onClick={() => setConfirm("false_positive")}
                >
                  Mark false positive
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirm("reset_baseline")}
                >
                  Reset baseline to current
                </Button>
              </div>
              {confirm === "resolve" || confirm === "false_positive" ? (
                <ConfirmStrip
                  title={
                    confirm === "false_positive"
                      ? "Mark as false positive?"
                      : "Resolve this alert?"
                  }
                  body={
                    confirm === "false_positive"
                      ? "Feeds §4.5.B.2 calibration (≤2% FP/week/agent). Notes required."
                      : "Writes resolution_notes. Empty notes blocked on high severity."
                  }
                  confirmLabel={
                    confirm === "false_positive"
                      ? "Confirm FP"
                      : "Confirm resolve"
                  }
                  onCancel={() => setConfirm(null)}
                  onConfirm={() => resolve(confirm === "false_positive")}
                />
              ) : null}
              {confirm === "reset_baseline" ? (
                <ConfirmStrip
                  title="Reset baseline to current?"
                  body="This makes today's behavior the new normal. Future alerts compare against this fingerprint window."
                  confirmLabel="Reset baseline"
                  tone="warn"
                  onCancel={() => setConfirm(null)}
                  onConfirm={resetBaseline}
                />
              ) : null}
              {alert.resolution_notes ? (
                <p className="text-[12px] text-muted-foreground">
                  Last notes:{" "}
                  <span className="text-foreground">
                    {alert.resolution_notes}
                  </span>
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card className={panelClass}>
            <CardHeader className="border-b border-border/60 px-4 py-3">
              <CardTitle className="text-[13px] font-medium">
                Staged action ladder
              </CardTitle>
              <p className="text-[12px] text-muted-foreground">
                Visible here — not buried in Settings (ADR 0047)
              </p>
            </CardHeader>
            <CardContent className="space-y-3 px-4 py-3 text-[12px]">
              <StageRow
                active={stage === "shadow"}
                label="Shadow (default)"
                detail={
                  shadowReady
                    ? "30-day shadow complete — promote available"
                    : `${shadowRemaining}d remaining of ${policy.shadow_days_required}d mandatory shadow (started ${policy.drift_shadow_started_at.slice(0, 10)})`
                }
              />
              <StageRow
                active={stage === "notify"}
                label="Notify-only"
                detail="Webhook / email / Slack to org owner on high severity"
                action={
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7"
                    disabled={!shadowReady || stage === "notify"}
                    title={
                      !shadowReady
                        ? `Locked until shadow window ends (${shadowRemaining}d left)`
                        : undefined
                    }
                    onClick={() => setConfirm("notify")}
                  >
                    Promote to notify
                  </Button>
                }
              />
              <StageRow
                active={stage === "auto_suspend"}
                label="Auto-suspend"
                detail="Off by default. Reuses ValidateAgent → AGENT_SUSPENDED"
                action={
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7"
                    disabled={stage !== "notify"}
                    title={
                      stage !== "notify"
                        ? "Promote to notify-only first"
                        : undefined
                    }
                    onClick={() => setConfirm("auto_suspend")}
                  >
                    Enable auto-suspend
                  </Button>
                }
              />
              {confirm === "notify" ? (
                <ConfirmStrip
                  title="Enable notify-only?"
                  body="Blast radius: high-severity drift.detected fires webhook, email, and Slack to the org owner. Logging-only shadow ends for this agent."
                  confirmLabel="Enable notify"
                  onCancel={() => setConfirm(null)}
                  onConfirm={() => promoteStage("notify")}
                />
              ) : null}
              {confirm === "auto_suspend" ? (
                <ConfirmStrip
                  title="Enable automatic suspension?"
                  body="High-severity drift can suspend this production agent. Enforcement path: ValidateAgent checks AGENT_SUSPENDED — the same gate used for manual suspend. This is not a bespoke code path."
                  confirmLabel="Enable auto-suspend"
                  tone="danger"
                  onCancel={() => setConfirm(null)}
                  onConfirm={() => promoteStage("auto_suspend")}
                />
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>

      <FingerprintHistory
        fingerprints={FINGERPRINTS_SUPPORT}
        alertWindowLabel={alertWindowLabel}
      />

      {alert.contributing_trace_ids.length > 0 ? (
        <Card className={panelClass}>
          <CardHeader className="border-b border-border/60 px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Recent traces that contributed to drift
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 py-3">
            <ul className="flex flex-wrap gap-2">
              {alert.contributing_trace_ids.map((id) => (
                <li key={id}>
                  <Button
                    asChild
                    size="sm"
                    variant="outline"
                    className="h-7 font-mono text-[12px]"
                  >
                    <Link href={`/dashboard/explore/t/${id}`}>{id}</Link>
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function Lane({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-border/70 px-3 py-2.5">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground">
        {title}
      </div>
      <div className="mt-1 text-[12px] leading-snug text-foreground">
        {body}
      </div>
    </div>
  )
}

function ConfirmStrip({
  title,
  body,
  confirmLabel,
  onCancel,
  onConfirm,
  tone = "default",
}: {
  title: string
  body: string
  confirmLabel: string
  onCancel: () => void
  onConfirm: () => void
  tone?: "default" | "warn" | "danger"
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2.5",
        tone === "danger" && "border-red-500/40 bg-red-500/5",
        tone === "warn" && "border-amber-500/40 bg-amber-500/5",
        tone === "default" && "border-border bg-muted/30",
      )}
    >
      <div className="font-medium text-foreground">{title}</div>
      <p className="mt-0.5 text-muted-foreground">{body}</p>
      <div className="mt-2 flex gap-2">
        <Button size="sm" variant="ghost" className="h-7" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          className="h-7"
          variant={tone === "danger" ? "destructive" : "default"}
          onClick={onConfirm}
        >
          {confirmLabel}
        </Button>
      </div>
    </div>
  )
}

function StageRow({
  active,
  label,
  detail,
  action,
}: {
  active: boolean
  label: string
  detail: string
  action?: React.ReactNode
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-2 rounded-md border px-2.5 py-2",
        active ? "border-foreground/30 bg-muted/40" : "border-border/60",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 font-medium text-foreground">
          {active ? (
            <span className="size-1.5 rounded-full bg-foreground" aria-hidden />
          ) : (
            <span
              className="size-1.5 rounded-full bg-muted-foreground/40"
              aria-hidden
            />
          )}
          {label}
        </div>
        <p className="mt-0.5 text-muted-foreground">{detail}</p>
      </div>
      {action}
    </div>
  )
}
