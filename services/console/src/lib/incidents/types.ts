/**
 * Failures, Incidents & Evidence Bundles (4.D.4) — finished-state contracts.
 *
 * Incidents are a purpose-built state machine on top of failed_tasks forensics.
 * Write-path rollback: set INCIDENT_WRITES_ENABLED false → read-only triage.
 */

export type IncidentSeverity = "sev1" | "sev2" | "sev3" | "sev4"

export type IncidentStatus =
  "open" | "acknowledged" | "mitigating" | "resolved" | "closed"

export type IncidentListItem = {
  incident_id: string
  severity: IncidentSeverity
  status: IncidentStatus
  title: string
  dedupe_key: string
  owner: string | null
  linked_trace_count: number
  linked_session_count: number
  age: string
  last_activity: string
  created_at: string
}

export type TimelineKind =
  | "state_transition"
  | "ownership"
  | "comment"
  | "link"
  | "bundle_export"
  | "severity"

export type TimelineEntry = {
  id: string
  kind: TimelineKind
  at: string
  actor: string
  summary: string
  before?: string
  after?: string
  /** Idempotent transition key — resubmit is a no-op, no duplicate audit. */
  transition_key?: string
}

export type LinkedEvidence = {
  kind: "trace" | "session" | "request"
  id: string
  label: string
  href: string
}

export type EvidenceBundle = {
  bundle_id: string
  signed: boolean
  hash: string
  exported_at: string
  exported_by: string
  contents: string[]
  no_secrets: boolean
  no_cross_tenant: boolean
  audit_event_id: string
}

export type IncidentDetail = IncidentListItem & {
  org: string
  description: string
  timeline: TimelineEntry[]
  linked: LinkedEvidence[]
  /** Sanitized by default; raw requires permission + audit. */
  payload_sanitized: string
  payload_raw_available: boolean
  directive_snapshot: {
    version: number
    hash: string
    at: string
  }
  bundles: EvidenceBundle[]
}

/** Rollback: false → read-only triage (milestone contract). */
export const INCIDENT_WRITES_ENABLED = true
