import { formatGovernAgeDays, formatGovernDate, formatGovernStamp } from "./govern-format"

export type DriftSeverity = "critical" | "warning" | "info"
export type DriftState = "open" | "acknowledged" | "snoozed" | "expected" | "resolved"

export const DRIFT_STATE_LABELS: Record<DriftState, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  snoozed: "Snoozed",
  expected: "Expected",
  resolved: "Resolved",
}

export const DRIFT_STATE_DEFINITIONS: Record<DriftState, string> = {
  open: "Outside its band and not yet reviewed. Needs an owner.",
  acknowledged: "Someone is looking. Acknowledgement records intent; it does not reset the baseline or clear the evidence.",
  snoozed: "Hidden until a chosen time. The monitor keeps evaluating.",
  expected: "Accepted as the new normal after a re-baseline approval.",
  resolved: "Back inside its band, or closed as not a problem.",
}

export const DRIFT_SEVERITY_LABELS: Record<DriftSeverity, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
}

export type DriftPoint = {
  date: string
  observed: number
  baseline: number
  low: number
  high: number
}

export type DriftMarker = {
  at: string
  label: string
  kind: "directive" | "policy" | "model" | "incident"
  href: string
}

export type DriftCause = {
  id: string
  kind: "directive" | "policy" | "model" | "incident"
  title: string
  at: string
  href: string
  detail: string
}

export type DriftRun = {
  runId: string
  at: string
  value: number
  durationSeconds: number
}

export type DriftActivity = {
  id: string
  at: string
  actor: string
  kind: "opened" | "state" | "owner" | "note" | "notification" | "cause"
  text: string
  eventId: string | null
}

export type DriftSignal = {
  id: string
  metric: string
  description: string
  agent: { id: string; name: string; version: string }
  severity: DriftSeverity
  state: DriftState
  openedAt: string
  firstSeen: string
  resolvedAt: string | null
  owner: string | null
  monitorId: string
  baselineId: string
  observed: number
  baseline: number
  threshold: number
  tolerance: number
  unit: string
  windowHours: number
  timeToDetectHours: number
  causeIds: string[]
  series: DriftPoint[]
  runsOutside: DriftRun[]
  runsInside: DriftRun[]
  activity: DriftActivity[]
}

export const driftCauses: DriftCause[] = [
  {
    id: "cause_support_v14",
    kind: "directive",
    title: "Directive promoted: Support triage v13 → v14",
    at: "2026-10-20T09:00:00Z",
    href: "/directives/dir_support_triage?tab=diff&from=v13&to=v14",
    detail: "Added refund lookup to the tool allowlist and made the refund flow the primary path.",
  },
  {
    id: "cause_policy_oct24",
    kind: "policy",
    title: "Policy snapshot published: pol_2026_10_24_01",
    at: "2026-10-24T03:00:00Z",
    href: "/policies/snapshots/pol_2026_10_24_01",
    detail: "Metadata-only release. No rule bytes changed, so it is a weak suspect.",
  },
  {
    id: "cause_policy_oct27",
    kind: "policy",
    title: "Policy snapshot published: pol_2026_10_27_03",
    at: "2026-10-27T03:00:00Z",
    href: "/policies/snapshots/pol_2026_10_27_03",
    detail: "Removed claude-sonnet-4 from the approved provider manifest.",
  },
]

export const driftMarkers: DriftMarker[] = [
  {
    at: "2026-10-20T09:00:00Z",
    label: "Promotion support-v14",
    kind: "directive",
    href: "/directives/dir_support_triage?tab=diff&from=v13&to=v14",
  },
  {
    at: "2026-10-24T03:00:00Z",
    label: "Snapshot pol_2026_10_24_01",
    kind: "policy",
    href: "/policies/snapshots/pol_2026_10_24_01",
  },
  {
    at: "2026-10-27T03:00:00Z",
    label: "Snapshot pol_2026_10_27_03",
    kind: "policy",
    href: "/policies/snapshots/pol_2026_10_27_03",
  },
]

function point(date: string, observed: number, baseline: number, tolerance: number): DriftPoint {
  return { date, observed, baseline, low: baseline - tolerance, high: baseline + tolerance }
}

function series(baseline: number, tolerance: number, values: number[]): DriftPoint[] {
  const dates = [
    "2026-10-17",
    "2026-10-18",
    "2026-10-19",
    "2026-10-20",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-24",
    "2026-10-25",
    "2026-10-26",
    "2026-10-27",
    "2026-10-28",
    "2026-10-29",
    "2026-10-30",
  ]
  return values.map((value, index) => point(dates[index]!, value, baseline, tolerance))
}

export const driftSignals: DriftSignal[] = [
  {
    id: "sig_tool_calls",
    metric: "Tool-call rate",
    description: "Average tool calls per run.",
    agent: { id: "ag_support_triage", name: "Support triage", version: "v14" },
    severity: "critical",
    state: "open",
    openedAt: "2026-10-21T09:14:00Z",
    firstSeen: "2026-10-21T09:14:00Z",
    resolvedAt: null,
    owner: null,
    monitorId: "mon_tool_rate",
    baselineId: "bl_support_v14",
    observed: 2.81,
    baseline: 1.2,
    threshold: 1.6,
    tolerance: 0.3,
    unit: "calls/run",
    windowHours: 6,
    timeToDetectHours: 4.2,
    causeIds: ["cause_support_v14"],
    series: series(1.2, 0.3, [1.12, 1.18, 1.21, 1.16, 2.42, 2.55, 2.61, 2.7, 2.66, 2.74, 2.69, 2.78, 2.81, 2.81]),
    runsOutside: [
      { runId: "run_5e92fb", at: "2026-10-27T18:21:00Z", value: 3.4, durationSeconds: 14.1 },
      { runId: "run_1f0b84", at: "2026-10-28T09:12:00Z", value: 3.2, durationSeconds: 12.4 },
      { runId: "run_2c81a4", at: "2026-10-29T11:47:00Z", value: 2.9, durationSeconds: 9.8 },
    ],
    runsInside: [
      { runId: "run_77b031", at: "2026-10-30T10:04:00Z", value: 1.1, durationSeconds: 8.2 },
      { runId: "run_9ac3d2", at: "2026-10-29T16:38:00Z", value: 1.2, durationSeconds: 7.9 },
      { runId: "run_4d10a3", at: "2026-10-30T08:53:00Z", value: 1.0, durationSeconds: 8.6 },
    ],
    activity: [
      {
        id: "act_tool_1",
        at: "2026-10-21T09:14:00Z",
        actor: "Drift monitor",
        kind: "opened",
        text: "Crossed the threshold for 6 hours. Opened as critical.",
        eventId: null,
      },
      {
        id: "act_tool_2",
        at: "2026-10-20T09:00:00Z",
        actor: "Directive service",
        kind: "cause",
        text: "Support triage v14 was promoted 1 day before the first observation.",
        eventId: "evt_7f3a21",
      },
      {
        id: "act_tool_3",
        at: "2026-10-22T09:14:00Z",
        actor: "Drift monitor",
        kind: "notification",
        text: "Reminded the on-call channel that the signal has no owner.",
        eventId: "evt_90bd14",
      },
    ],
  },
  {
    id: "sig_retrieval_mix",
    metric: "Retrieval mix",
    description: "Share of runs that retrieve from the refund knowledge base.",
    agent: { id: "ag_support_triage", name: "Support triage", version: "v14" },
    severity: "warning",
    state: "acknowledged",
    openedAt: "2026-10-24T08:30:00Z",
    firstSeen: "2026-10-24T08:30:00Z",
    resolvedAt: null,
    owner: "Priya Nair",
    monitorId: "mon_retrieval_mix",
    baselineId: "bl_support_v14",
    observed: 0.48,
    baseline: 0.3,
    threshold: 0.4,
    tolerance: 0.05,
    unit: "share",
    windowHours: 12,
    timeToDetectHours: 5.5,
    causeIds: ["cause_policy_oct24"],
    series: series(0.3, 0.05, [0.29, 0.31, 0.3, 0.28, 0.33, 0.34, 0.34, 0.41, 0.42, 0.45, 0.44, 0.47, 0.46, 0.48]),
    runsOutside: [
      { runId: "run_2c81a4", at: "2026-10-29T11:47:00Z", value: 0.52, durationSeconds: 9.8 },
      { runId: "run_1f0b84", at: "2026-10-28T09:12:00Z", value: 0.49, durationSeconds: 12.4 },
      { runId: "run_5e92fb", at: "2026-10-27T18:21:00Z", value: 0.46, durationSeconds: 14.1 },
    ],
    runsInside: [
      { runId: "run_77b031", at: "2026-10-30T10:04:00Z", value: 0.29, durationSeconds: 8.2 },
      { runId: "run_9ac3d2", at: "2026-10-29T16:38:00Z", value: 0.31, durationSeconds: 7.9 },
      { runId: "run_4d10a3", at: "2026-10-30T08:53:00Z", value: 0.3, durationSeconds: 8.6 },
    ],
    activity: [
      {
        id: "act_mix_1",
        at: "2026-10-24T08:30:00Z",
        actor: "Drift monitor",
        kind: "opened",
        text: "Crossed the threshold for 12 hours. Opened as warning.",
        eventId: null,
      },
      {
        id: "act_mix_2",
        at: "2026-10-24T10:02:00Z",
        actor: "Priya Nair",
        kind: "owner",
        text: "Assigned to Priya Nair.",
        eventId: null,
      },
      {
        id: "act_mix_3",
        at: "2026-10-24T10:03:00Z",
        actor: "Priya Nair",
        kind: "state",
        text: "Acknowledged. The signal stays open until it returns inside the band.",
        eventId: null,
      },
    ],
  },
  {
    id: "sig_latency_shift",
    metric: "Latency p95",
    description: "95th percentile end-to-end latency.",
    agent: { id: "ag_billing_assistant", name: "Billing assistant", version: "v9" },
    severity: "warning",
    state: "resolved",
    openedAt: "2026-10-22T06:00:00Z",
    firstSeen: "2026-10-22T06:00:00Z",
    resolvedAt: "2026-10-26T18:00:00Z",
    owner: "Jon Park",
    monitorId: "mon_latency_p95",
    baselineId: "bl_billing_v9",
    observed: 2.1,
    baseline: 1.4,
    threshold: 1.75,
    tolerance: 0.2,
    unit: "seconds",
    windowHours: 3,
    timeToDetectHours: 2.4,
    causeIds: [],
    series: series(1.4, 0.2, [1.38, 1.42, 1.4, 1.45, 1.36, 2.2, 2.1, 1.98, 1.82, 1.66, 1.52, 1.44, 1.4, 1.41]),
    runsOutside: [
      { runId: "run_9ac3d2", at: "2026-10-24T16:38:00Z", value: 2.2, durationSeconds: 9.4 },
      { runId: "run_8ad1c0", at: "2026-10-25T14:06:00Z", value: 2.0, durationSeconds: 8.9 },
    ],
    runsInside: [
      { runId: "run_77b031", at: "2026-10-30T10:04:00Z", value: 1.4, durationSeconds: 7.1 },
      { runId: "run_4d10a3", at: "2026-10-30T08:53:00Z", value: 1.38, durationSeconds: 7.4 },
    ],
    activity: [
      {
        id: "act_lat_1",
        at: "2026-10-22T06:00:00Z",
        actor: "Drift monitor",
        kind: "opened",
        text: "Crossed the threshold for 3 evaluations. Opened as warning.",
        eventId: null,
      },
      {
        id: "act_lat_2",
        at: "2026-10-22T08:30:00Z",
        actor: "Jon Park",
        kind: "state",
        text: "Acknowledged while the provider incident was investigated.",
        eventId: null,
      },
      {
        id: "act_lat_3",
        at: "2026-10-26T18:00:00Z",
        actor: "Drift monitor",
        kind: "state",
        text: "Back inside the band for 24 hours. Resolved automatically.",
        eventId: null,
      },
    ],
  },
]

export type DriftBaselineMetric = {
  name: string
  baseline: number
  low: number
  high: number
  unit: string
}

export type DriftRebaseline = {
  id: string
  at: string
  by: string
  why: string
}

export type DriftBaseline = {
  id: string
  agent: { id: string; name: string; version: string }
  windowFrom: string
  windowTo: string
  certifiedBy: string
  certifiedAt: string
  evidence: "certified" | "sampled"
  runs: number
  sampleRuns: string[]
  metrics: DriftBaselineMetric[]
  history: DriftRebaseline[]
}

export const driftBaselines: DriftBaseline[] = [
  {
    id: "bl_support_v14",
    agent: { id: "ag_support_triage", name: "Support triage", version: "v14" },
    windowFrom: "2026-09-01T00:00:00Z",
    windowTo: "2026-09-12T00:00:00Z",
    certifiedBy: "Priya Nair",
    certifiedAt: "2026-09-12T10:20:00Z",
    evidence: "certified",
    runs: 486,
    sampleRuns: ["run_77b031", "run_9ac3d2", "run_1f0b84"],
    metrics: [
      { name: "Tool-call rate", baseline: 1.2, low: 0.9, high: 1.5, unit: "calls/run" },
      { name: "Retrieval mix", baseline: 0.3, low: 0.25, high: 0.35, unit: "share" },
      { name: "Latency p95", baseline: 1.4, low: 1.2, high: 1.6, unit: "seconds" },
      { name: "Error rate", baseline: 0.8, low: 0.4, high: 1.2, unit: "%" },
      { name: "Cost per run", baseline: 0.042, low: 0.03, high: 0.055, unit: "USD" },
    ],
    history: [
      { id: "reb_support_1", at: "2026-09-12T10:20:00Z", by: "Priya Nair", why: "Certified after the tool allowlist change." },
      { id: "reb_support_2", at: "2026-08-02T14:05:00Z", by: "Mira Chen", why: "Re-baselined after signal #9 (context window change)." },
    ],
  },
  {
    id: "bl_billing_v9",
    agent: { id: "ag_billing_assistant", name: "Billing assistant", version: "v9" },
    windowFrom: "2026-09-20T00:00:00Z",
    windowTo: "2026-10-02T00:00:00Z",
    certifiedBy: "Jon Park",
    certifiedAt: "2026-10-02T16:40:00Z",
    evidence: "certified",
    runs: 322,
    sampleRuns: ["run_8ad1c0", "run_9ac3d2"],
    metrics: [
      { name: "Tool-call rate", baseline: 0.9, low: 0.65, high: 1.15, unit: "calls/run" },
      { name: "Latency p95", baseline: 1.4, low: 1.2, high: 1.6, unit: "seconds" },
      { name: "Error rate", baseline: 1.1, low: 0.6, high: 1.6, unit: "%" },
      { name: "Cost per run", baseline: 0.037, low: 0.028, high: 0.048, unit: "USD" },
    ],
    history: [{ id: "reb_billing_1", at: "2026-10-02T16:40:00Z", by: "Jon Park", why: "Certified after the v9 promotion." }],
  },
  {
    id: "bl_incident_v5",
    agent: { id: "ag_incident_responder", name: "Incident responder", version: "v5" },
    windowFrom: "2026-06-20T00:00:00Z",
    windowTo: "2026-07-20T00:00:00Z",
    certifiedBy: "Mira Chen",
    certifiedAt: "2026-07-20T09:15:00Z",
    evidence: "sampled",
    runs: 148,
    sampleRuns: ["run_4d10a3"],
    metrics: [
      { name: "Tool-call rate", baseline: 1.6, low: 1.3, high: 1.9, unit: "calls/run" },
      { name: "Latency p95", baseline: 2.1, low: 1.8, high: 2.4, unit: "seconds" },
      { name: "Error rate", baseline: 1.4, low: 0.8, high: 2.0, unit: "%" },
      { name: "Cost per run", baseline: 0.061, low: 0.048, high: 0.074, unit: "USD" },
    ],
    history: [{ id: "reb_incident_1", at: "2026-07-20T09:15:00Z", by: "Mira Chen", why: "Initial baseline from sampled runs." }],
  },
]

export type DriftMonitorStatus = "ok" | "firing" | "no_data" | "muted"

export type DriftMonitorEvaluation = {
  at: string
  value: number | null
  result: DriftMonitorStatus
  note: string
}

export type DriftMonitor = {
  id: string
  metric: string
  description: string
  appliesTo: string[]
  rule: string
  severity: DriftSeverity
  lastEvaluated: string | null
  status: DriftMonitorStatus
  reason: string | null
  notifies: string | null
  signalId: string | null
  unit: string | null
  evaluations: DriftMonitorEvaluation[]
}

export const driftMonitors: DriftMonitor[] = [
  {
    id: "mon_tool_rate",
    metric: "Tool-call rate",
    description: "Average tool calls per run for an agent version.",
    appliesTo: ["Support triage · v14"],
    rule: "> baseline × 1.33 for 6h",
    severity: "critical",
    lastEvaluated: "2026-10-30T15:08:00Z",
    status: "firing",
    reason: null,
    notifies: "#agent-ops",
    signalId: "sig_tool_calls",
    unit: "calls/run",
    evaluations: [
      { at: "2026-10-30T15:08:00Z", value: 2.81, result: "firing", note: "Above 1.60 threshold." },
      { at: "2026-10-30T14:08:00Z", value: 2.79, result: "firing", note: "Above 1.60 threshold." },
      { at: "2026-10-30T13:08:00Z", value: 2.8, result: "firing", note: "Above 1.60 threshold." },
    ],
  },
  {
    id: "mon_retrieval_mix",
    metric: "Retrieval mix",
    description: "Share of runs that retrieve from the refund knowledge base.",
    appliesTo: ["Support triage · v14"],
    rule: "> baseline × 1.33 for 12h",
    severity: "warning",
    lastEvaluated: "2026-10-30T15:02:00Z",
    status: "firing",
    reason: null,
    notifies: "Priya Nair",
    signalId: "sig_retrieval_mix",
    unit: "share",
    evaluations: [
      { at: "2026-10-30T15:02:00Z", value: 0.48, result: "firing", note: "Above 0.40 threshold." },
      { at: "2026-10-30T14:02:00Z", value: 0.47, result: "firing", note: "Above 0.40 threshold." },
      { at: "2026-10-30T13:02:00Z", value: 0.46, result: "firing", note: "Above 0.40 threshold." },
    ],
  },
  {
    id: "mon_latency_p95",
    metric: "Latency p95",
    description: "95th percentile end-to-end latency for an agent version.",
    appliesTo: ["Billing assistant · v9"],
    rule: "> 1.75s for 3 evaluations",
    severity: "warning",
    lastEvaluated: "2026-10-30T15:00:00Z",
    status: "ok",
    reason: null,
    notifies: "#billing-ops",
    signalId: "sig_latency_shift",
    unit: "seconds",
    evaluations: [
      { at: "2026-10-30T15:00:00Z", value: 1.41, result: "ok", note: "Inside the band." },
      { at: "2026-10-30T14:00:00Z", value: 1.4, result: "ok", note: "Inside the band." },
      { at: "2026-10-30T13:00:00Z", value: 1.42, result: "ok", note: "Inside the band." },
    ],
  },
  {
    id: "mon_error_fingerprint",
    metric: "Error fingerprint",
    description: "New error fingerprints that did not exist in the baseline window.",
    appliesTo: ["Incident responder · v5"],
    rule: "new fingerprint in 24h",
    severity: "warning",
    lastEvaluated: null,
    status: "no_data",
    reason: "No runs in 24h",
    notifies: "No one",
    signalId: null,
    unit: null,
    evaluations: [],
  },
  {
    id: "mon_cost_run",
    metric: "Cost per run",
    description: "Mean provider cost per run.",
    appliesTo: ["All agents"],
    rule: "> baseline × 1.5 for 24h",
    severity: "info",
    lastEvaluated: "2026-10-30T14:58:00Z",
    status: "ok",
    reason: null,
    notifies: "#finops",
    signalId: null,
    unit: "USD",
    evaluations: [
      { at: "2026-10-30T14:58:00Z", value: 0.045, result: "ok", note: "Inside the band." },
      { at: "2026-10-30T13:58:00Z", value: 0.044, result: "ok", note: "Inside the band." },
    ],
  },
  {
    id: "mon_refusal",
    metric: "Refusal rate",
    description: "Share of responses that refuse the request.",
    appliesTo: ["Onboarding guide · v2"],
    rule: "> 5% for 6h",
    severity: "info",
    lastEvaluated: "2026-10-30T12:00:00Z",
    status: "muted",
    reason: "Muted until the onboarding rewrite ships",
    notifies: "No one",
    signalId: null,
    unit: "%",
    evaluations: [{ at: "2026-10-30T12:00:00Z", value: 2.1, result: "muted", note: "Monitor muted by Jon Park." }],
  },
]

export function driftSignalById(signalId: string | null | undefined): DriftSignal | null {
  if (!signalId) return null
  return driftSignals.find((signal) => signal.id === signalId) ?? null
}

export function driftBaselineById(baselineId: string | null | undefined): DriftBaseline | null {
  if (!baselineId) return null
  return driftBaselines.find((baseline) => baseline.id === baselineId) ?? null
}

export function driftBaselineForAgent(agentId: string): DriftBaseline | null {
  return driftBaselines.find((baseline) => baseline.agent.id === agentId) ?? null
}

export function driftMonitorById(monitorId: string | null | undefined): DriftMonitor | null {
  if (!monitorId) return null
  return driftMonitors.find((monitor) => monitor.id === monitorId) ?? null
}

export function driftCauseById(causeId: string): DriftCause | null {
  return driftCauses.find((cause) => cause.id === causeId) ?? null
}

export type DriftChange = {
  ratio: number
  label: string
  percent: number
}

/** Brief §8.5: "×" when the ratio is at least 2, otherwise a percentage. */
export function driftChange(signal: Pick<DriftSignal, "observed" | "baseline">): DriftChange {
  const ratio = signal.baseline === 0 ? 0 : signal.observed / signal.baseline
  const percent = Math.round((ratio - 1) * 100)
  return {
    ratio,
    label: ratio >= 2 ? `${ratio.toFixed(1)}×` : `${percent > 0 ? "+" : ""}${percent}%`,
    percent,
  }
}

export function driftSuspectedCauses(signal: DriftSignal): { cause: DriftCause; hoursBefore: number; label: string }[] {
  const firstSeen = Date.parse(signal.firstSeen)
  return signal.causeIds
    .map((causeId) => driftCauseById(causeId))
    .filter((cause): cause is DriftCause => Boolean(cause))
    .map((cause) => {
      const hoursBefore = Math.round(((firstSeen - Date.parse(cause.at)) / 3_600_000) * 10) / 10
      return { cause, hoursBefore, label: driftBeforeLabel(hoursBefore) }
    })
    .filter((entry) => entry.hoursBefore >= 0 && entry.hoursBefore <= 72)
    .sort((left, right) => left.hoursBefore - right.hoursBefore)
}

export function driftBeforeLabel(hoursBefore: number): string {
  if (hoursBefore < 1) return `${Math.max(1, Math.round(hoursBefore * 60))} minutes before`
  if (hoursBefore < 24) return `${Math.round(hoursBefore)} hours before`
  const days = Math.round(hoursBefore / 24)
  return `${days} ${days === 1 ? "day" : "days"} before`
}

export function driftOpenSignals(): DriftSignal[] {
  return driftSignals.filter((signal) => signal.state === "open" || signal.state === "acknowledged")
}

export type DriftAttention = {
  needsOwner: { count: number; critical: number }
  outOfBand: { count: number; worst: DriftSignal | null }
  recentChanges: { count: number; label: string | null }
}

export function driftAttention(): DriftAttention {
  const active = driftOpenSignals()
  const unowned = active.filter((signal) => !signal.owner)
  const outside = active.filter(
    (signal) => signal.observed > signal.threshold || signal.observed > signal.baseline + signal.tolerance,
  )
  const worst = [...outside].sort((left, right) => driftChange(right).ratio - driftChange(left).ratio)[0] ?? null
  const causes = active.flatMap((signal) => driftSuspectedCauses(signal))
  const promotion = causes.find((entry) => entry.cause.kind === "directive") ?? null
  return {
    needsOwner: {
      count: unowned.length,
      critical: unowned.filter((signal) => signal.severity === "critical").length,
    },
    outOfBand: { count: outside.length, worst },
    recentChanges: {
      count: promotion ? 1 : 0,
      label: promotion ? `${promotion.cause.title.replace(/^Directive promoted: /, "")}, ${formatGovernDate(promotion.cause.at)}` : null,
    },
  }
}

export function driftStatusLine(): { tone: "ok" | "warning" | "muted"; text: string } {
  const active = driftOpenSignals()
  if (!active.length) {
    return { tone: "ok", text: `No open signals. ${driftMonitors.length} monitors are watching 4 agents; last evaluated ${formatGovernStamp(driftMonitors[0]?.lastEvaluated)}.` }
  }
  const critical = active.filter((signal) => signal.severity === "critical").length
  const warning = active.filter((signal) => signal.severity === "warning").length
  const agents = new Set(active.map((signal) => signal.agent.id)).size
  const oldest = active
    .map((signal) => Math.floor((Date.parse("2026-10-30T15:12:00Z") - Date.parse(signal.openedAt)) / 86_400_000))
    .sort((left, right) => right - left)[0]!
  const parts = [critical ? `${critical} critical` : null, warning ? `${warning} warning` : null].filter(Boolean).join(" and ")
  return {
    tone: critical ? "warning" : "ok",
    text: `${active.length} signal${active.length === 1 ? " is" : "s are"} open across ${agents} agent${agents === 1 ? "" : "s"}: ${parts}. The oldest has been open ${oldest} ${oldest === 1 ? "day" : "days"}.`,
  }
}

export type DriftListState = {
  q: string
  state: DriftState | "active" | "all"
  severity: DriftSeverity | "all"
  owner: string
  agent: string
  sort: "severity" | "opened" | "change"
  cause: "all" | "recent"
}

export function filterDriftSignals(signals: DriftSignal[], state: DriftListState): DriftSignal[] {
  const query = state.q.trim().toLowerCase()
  return signals.filter((signal) => {
    if (state.state === "active" && signal.state !== "open" && signal.state !== "acknowledged") return false
    if (state.state !== "active" && state.state !== "all" && signal.state !== state.state) return false
    if (state.severity !== "all" && signal.severity !== state.severity) return false
    if (state.owner === "none" && signal.owner) return false
    if (state.owner !== "all" && state.owner !== "none" && signal.owner !== state.owner) return false
    if (state.agent !== "all" && signal.agent.id !== state.agent) return false
    if (state.cause === "recent" && driftSuspectedCauses(signal).length === 0) return false
    if (!query) return true
    return [signal.metric, signal.agent.name, signal.agent.version, signal.description].some((value) =>
      value.toLowerCase().includes(query),
    )
  })
}

const SEVERITY_ORDER: Record<DriftSeverity, number> = { critical: 0, warning: 1, info: 2 }

export function sortDriftSignals(signals: DriftSignal[], sort: DriftListState["sort"]): DriftSignal[] {
  return [...signals].sort((left, right) => {
    if (sort === "opened") return Date.parse(left.openedAt) - Date.parse(right.openedAt)
    if (sort === "change") return driftChange(right).ratio - driftChange(left).ratio
    const severity = SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity]
    return severity !== 0 ? severity : Date.parse(left.openedAt) - Date.parse(right.openedAt)
  })
}

export function driftOwnerOptions(): string[] {
  return [...new Set(driftSignals.map((signal) => signal.owner).filter((owner): owner is string => Boolean(owner)))]
}

export function driftAgentOptions(): { id: string; label: string }[] {
  const seen = new Map<string, string>()
  for (const signal of driftSignals) seen.set(signal.agent.id, `${signal.agent.name} · ${signal.agent.version}`)
  return [...seen.entries()].map(([id, label]) => ({ id, label }))
}

export function driftSummarySentence(signal: DriftSignal): string {
  const change = driftChange(signal)
  return `${signal.agent.name} ${signal.agent.version} recorded ${formatDriftValue(signal.observed, signal.unit)}, ${change.label} its certified baseline of ${formatDriftValue(signal.baseline, signal.unit)}. The signal crossed the threshold (${formatDriftValue(signal.threshold, signal.unit)}) at ${formatGovernStamp(signal.firstSeen)}.`
}

export function formatDriftValue(value: number, unit: string): string {
  if (unit === "share") return `${Math.round(value * 100)}%`
  if (unit === "seconds") return `${value.toFixed(2)}s`
  if (unit === "USD") return `$${value.toFixed(3)}`
  if (unit === "%") return `${value.toFixed(1)}%`
  return `${value.toFixed(2)} ${unit}`
}

export function driftMonitorValue(monitor: Pick<DriftMonitor, "unit">, value: number | null): string {
  if (value === null) return "Not recorded"
  return monitor.unit ? formatDriftValue(value, monitor.unit) : value.toFixed(2)
}

export function driftBaselineAge(baseline: DriftBaseline): number | null {
  return formatGovernAgeDays(baseline.certifiedAt)
}

export function driftBaselineTone(baseline: DriftBaseline): "ok" | "warning" | "critical" {
  const age = driftBaselineAge(baseline)
  if (age === null) return "ok"
  if (age > 90) return "critical"
  if (age > 30) return "warning"
  return "ok"
}

export function driftSignalsForBaseline(baselineId: string): DriftSignal[] {
  return driftSignals.filter((signal) => signal.baselineId === baselineId && (signal.state === "open" || signal.state === "acknowledged"))
}

export function driftMonitorsForAgent(agent: { name: string; version: string }): DriftMonitor[] {
  const label = `${agent.name} · ${agent.version}`
  return driftMonitors.filter((monitor) => monitor.appliesTo.includes(label) || monitor.appliesTo.includes("All agents"))
}

export function driftMarkerValues(signal: DriftSignal): DriftMarker[] {
  const from = Date.parse(signal.series[0]!.date)
  const to = Date.parse(signal.series.at(-1)!.date) + 86_400_000
  return driftMarkers.filter((marker) => {
    const time = Date.parse(marker.at)
    return time >= from && time <= to
  })
}
