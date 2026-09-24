"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { CopyId } from "@/components/explore/copy-id"
import { exploreTable } from "@/components/explore/table-styles"
import {
  IncidentStatusBadge,
  SeverityBadge,
} from "@/components/incidents/status-badges"
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
import { BUNDLE_SAMPLE } from "@/lib/incidents/fixtures"
import type {
  EvidenceBundle,
  IncidentDetail,
  IncidentSeverity,
  IncidentStatus,
  TimelineEntry,
} from "@/lib/incidents/types"
import { INCIDENT_WRITES_ENABLED } from "@/lib/incidents/types"
import { cn } from "@/lib/utils"

const NEXT_STATUS: Partial<Record<IncidentStatus, IncidentStatus>> = {
  open: "acknowledged",
  acknowledged: "mitigating",
  mitigating: "resolved",
  resolved: "closed",
}

export function IncidentDetailView({
  incident: initial,
}: {
  incident: IncidentDetail
}) {
  const [incident, setIncident] = React.useState(initial)
  const [comment, setComment] = React.useState("")
  const [rawUnlocked, setRawUnlocked] = React.useState(false)
  const [bundles, setBundles] = React.useState<EvidenceBundle[]>(
    initial.bundles,
  )
  const appliedKeys = React.useRef(
    new Set(
      initial.timeline
        .map((t) => t.transition_key)
        .filter((k): k is string => Boolean(k)),
    ),
  )

  const applyTransition = (to: IncidentStatus, note?: string) => {
    if (!INCIDENT_WRITES_ENABLED) {
      toast.error("Write path rolled back — read-only triage")
      return
    }
    const key = `${incident.incident_id}:${to}`
    if (appliedKeys.current.has(key)) {
      toast.message("Idempotent no-op", {
        description:
          "Same transition already applied — no duplicate audit row.",
      })
      return
    }
    appliedKeys.current.add(key)
    const entry: TimelineEntry = {
      id: `tl_${Date.now()}`,
      kind: "state_transition",
      at: new Date().toISOString(),
      actor: "operator",
      summary: note ? `→ ${to} · ${note}` : `→ ${to}`,
      before: incident.status,
      after: to,
      transition_key: key,
    }
    setIncident((prev) => ({
      ...prev,
      status: to,
      last_activity: "just now",
      timeline: [...prev.timeline, entry],
    }))
    toast.success(`Status → ${to}`, {
      description: "Audited transition recorded.",
    })
  }

  const reassign = (owner: string) => {
    if (!INCIDENT_WRITES_ENABLED) {
      toast.error("Write path rolled back — read-only triage")
      return
    }
    const entry: TimelineEntry = {
      id: `tl_${Date.now()}`,
      kind: "ownership",
      at: new Date().toISOString(),
      actor: "operator",
      summary: `reassigned → @${owner}`,
      before: incident.owner ?? "unassigned",
      after: owner,
    }
    setIncident((prev) => ({
      ...prev,
      owner,
      timeline: [...prev.timeline, entry],
    }))
    toast.success(`Owner → @${owner}`)
  }

  const changeSeverity = (severity: IncidentSeverity) => {
    if (!INCIDENT_WRITES_ENABLED) {
      toast.error("Write path rolled back — read-only triage")
      return
    }
    const entry: TimelineEntry = {
      id: `tl_${Date.now()}`,
      kind: "severity",
      at: new Date().toISOString(),
      actor: "operator",
      summary: `severity ${incident.severity} → ${severity}`,
      before: incident.severity,
      after: severity,
    }
    setIncident((prev) => ({
      ...prev,
      severity,
      timeline: [...prev.timeline, entry],
    }))
    toast.success(`Severity → ${severity}`, {
      description: "Audited severity change.",
    })
  }

  const addComment = () => {
    if (!comment.trim()) return
    if (!INCIDENT_WRITES_ENABLED) {
      toast.error("Write path rolled back — read-only triage")
      return
    }
    const entry: TimelineEntry = {
      id: `tl_${Date.now()}`,
      kind: "comment",
      at: new Date().toISOString(),
      actor: "operator",
      summary: comment.trim(),
    }
    setIncident((prev) => ({
      ...prev,
      timeline: [...prev.timeline, entry],
    }))
    setComment("")
    toast.success("Comment added")
  }

  const exportBundle = () => {
    if (!INCIDENT_WRITES_ENABLED) {
      toast.error("Write path rolled back — read-only triage")
      return
    }
    const bundle: EvidenceBundle = {
      ...BUNDLE_SAMPLE,
      bundle_id: `bundle_${Date.now().toString(36)}`,
      exported_at: new Date().toISOString(),
      exported_by: "operator",
      audit_event_id: `audit_${Date.now().toString(36)}`,
    }
    const entry: TimelineEntry = {
      id: `tl_${Date.now()}`,
      kind: "bundle_export",
      at: bundle.exported_at,
      actor: bundle.exported_by,
      summary: `exported signed bundle ${bundle.bundle_id} · ${bundle.hash}`,
    }
    setBundles((b) => [bundle, ...b])
    setIncident((prev) => ({
      ...prev,
      timeline: [...prev.timeline, entry],
    }))
    toast.success("Signed evidence bundle ready", {
      description: `${bundle.hash} · audit ${bundle.audit_event_id}`,
    })
  }

  const next = NEXT_STATUS[incident.status]

  return (
    <div className="space-y-3">
      {!INCIDENT_WRITES_ENABLED && (
        <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
          Write path rolled back — read-only triage. Existing bundles remain
          readable; mutating actions are blocked.
        </p>
      )}

      <Card className={panelClass}>
        <CardHeader className="gap-3 border-b px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <CopyId
              value={incident.incident_id}
              label="incident_id"
              className="font-mono text-[13px] font-medium"
            />
            <SeverityBadge severity={incident.severity} />
            <IncidentStatusBadge status={incident.status} />
            <span className="font-mono text-[13px] text-muted-foreground">
              owner: @{incident.owner ?? "unassigned"}
            </span>
          </div>
          <CardTitle className="text-[13px] font-medium leading-5">
            {incident.title}
          </CardTitle>
          <p className="text-[13px] leading-5 text-muted-foreground">
            {incident.description}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={incident.severity}
              onValueChange={(v) => changeSeverity(v as IncidentSeverity)}
              disabled={!INCIDENT_WRITES_ENABLED}
            >
              <SelectTrigger
                size="sm"
                className="w-full max-w-[110px] sm:w-[110px]"
                aria-label="Severity"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["sev1", "sev2", "sev3", "sev4"] as const).map((s) => (
                  <SelectItem key={s} value={s}>
                    {s.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              disabled={!INCIDENT_WRITES_ENABLED}
              onClick={() =>
                reassign(incident.owner === "sara" ? "devon" : "sara")
              }
            >
              Reassign
            </Button>
            {next && (
              <Button
                size="sm"
                disabled={!INCIDENT_WRITES_ENABLED}
                onClick={() => applyTransition(next)}
              >
                → {next}
              </Button>
            )}
            {incident.status === "mitigating" && (
              <Button
                size="sm"
                variant="outline"
                disabled={!INCIDENT_WRITES_ENABLED}
                onClick={() => applyTransition("resolved")}
              >
                Resolve
              </Button>
            )}
            {incident.status === "resolved" && (
              <Button
                size="sm"
                variant="outline"
                disabled={!INCIDENT_WRITES_ENABLED}
                onClick={() => applyTransition("closed")}
              >
                Close
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              disabled={!INCIDENT_WRITES_ENABLED}
              onClick={exportBundle}
            >
              Export Evidence Bundle
            </Button>
          </div>
          <p className="font-mono text-[13px] text-muted-foreground">
            dedupe_key: {incident.dedupe_key} · {incident.linked_trace_count}{" "}
            traces · {incident.linked_session_count} sessions · directive v
            {incident.directive_snapshot.version} (
            {incident.directive_snapshot.hash})
          </p>
        </CardHeader>
      </Card>

      <div className="grid items-start gap-3 lg:grid-cols-2">
        <Card className={panelClass}>
          <CardHeader className="gap-1 border-b px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Linked evidence
            </CardTitle>
            <p className="text-[13px] text-muted-foreground">
              Clickable pivots into Explore / Sessions with context preserved.
            </p>
          </CardHeader>
          <CardContent className="space-y-2 px-4 py-3 text-[13px]">
            {incident.linked.map((l) => (
              <Link
                key={`${l.kind}-${l.id}`}
                href={l.href}
                className={cn(
                  exploreTable.mono,
                  "block rounded-md border px-3 py-2 hover:bg-muted/50",
                )}
              >
                <span className="text-muted-foreground">{l.kind}</span>{" "}
                {l.label}
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card className={panelClass}>
          <CardHeader className="gap-1 border-b px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Failure payload
            </CardTitle>
            <p className="text-[13px] text-muted-foreground">
              Sanitized by default (F4-008). Raw view is permission-gated +
              audited.
            </p>
          </CardHeader>
          <CardContent className="space-y-2 px-4 py-3">
            <pre className="overflow-x-auto rounded-md bg-muted/50 p-3 font-mono text-[13px] leading-5 whitespace-pre-wrap">
              {rawUnlocked && incident.payload_raw_available
                ? incident.payload_sanitized.replace("[sanitized]", "FULL_RAW")
                : incident.payload_sanitized}
            </pre>
            {incident.payload_raw_available && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  toast.message("raw:read + audit event", {
                    description:
                      "Viewing sensitive payload would emit an audit entry.",
                  })
                  setRawUnlocked(true)
                }}
              >
                View raw (permission-gated)
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className={panelClass}>
        <CardHeader className="gap-1 border-b px-4 py-3">
          <CardTitle className="text-[13px] font-medium">Timeline</CardTitle>
          <p className="text-[13px] text-muted-foreground">
            State transitions, ownership, comments, links — each with actor,
            timestamp, before/after. Transitions are idempotent.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3">
          <ul className="space-y-2.5">
            {incident.timeline.map((t) => (
              <li
                key={t.id}
                className="grid gap-0.5 border-b border-border/60 pb-2.5 last:border-0 last:pb-0 font-mono text-[13px] leading-5"
              >
                <div className="flex flex-wrap gap-x-2 text-muted-foreground">
                  <span>{t.at.slice(11, 16)}</span>
                  <span>@{t.actor}</span>
                  <span className="text-foreground/70">{t.kind}</span>
                </div>
                <div>{t.summary}</div>
                {(t.before || t.after) && (
                  <div className="text-[13px] text-muted-foreground">
                    {t.before ?? "—"} → {t.after ?? "—"}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2 pt-1">
            <Input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add a comment…"
              className="h-9 max-w-md text-[13px]"
              disabled={!INCIDENT_WRITES_ENABLED}
              onKeyDown={(e) => {
                if (e.key === "Enter") addComment()
              }}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={!INCIDENT_WRITES_ENABLED}
              onClick={addComment}
            >
              Comment
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardHeader className="gap-1 border-b px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Evidence bundles
          </CardTitle>
          <p className="text-[13px] text-muted-foreground">
            Signed exports survive telemetry TTL — no secrets, no cross-tenant
            data. Download emits an audit event.
          </p>
        </CardHeader>
        <CardContent className="space-y-2 px-4 py-3 text-[13px]">
          {bundles.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">
              No bundles yet — export to produce a postmortem-ready artifact.
            </p>
          ) : (
            bundles.map((b) => (
              <div
                key={b.bundle_id}
                className="rounded-md border px-3 py-2 font-mono text-[13px] leading-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{b.bundle_id}</span>
                  {b.signed && (
                    <span className="rounded border border-emerald-600/40 px-1.5 text-[13px] text-emerald-800 dark:text-emerald-300">
                      signed
                    </span>
                  )}
                </div>
                <div className="mt-1 text-muted-foreground">
                  {b.hash} · by @{b.exported_by} · {b.exported_at}
                </div>
                <div className="mt-1 text-muted-foreground">
                  {b.contents.join(" · ")}
                </div>
                <div className="mt-1 text-[13px] text-muted-foreground">
                  no_secrets={String(b.no_secrets)} · no_cross_tenant=
                  {String(b.no_cross_tenant)} · audit {b.audit_event_id}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2"
                  onClick={() =>
                    toast.success("Download started", {
                      description: `Audit ${b.audit_event_id} recorded.`,
                    })
                  }
                >
                  Download
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
