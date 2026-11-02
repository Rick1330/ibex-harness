import {
  POLICY_AREA_ORDER,
  POLICY_DECISION_ORDER,
  POLICY_EFFECT_FILTER_LABELS,
  POLICY_MODE_FILTER_LABELS,
  POLICY_RULE_TABS,
  policySnapshots,
  type PolicyArea,
  type PolicyDecisionKind,
  type PolicyEffectFilter,
  type PolicyModeFilter,
  type PolicyRuleTab,
} from "./policy-preview"
import {
  DRIFT_SEVERITY_LABELS,
  DRIFT_STATE_LABELS,
  type DriftListState,
  type DriftMonitorStatus,
  type DriftSeverity,
  type DriftState,
} from "./drift-preview"
import {
  AUDIT_EXPORT_FORMATS,
  AUDIT_ORIGIN_LABELS,
  AUDIT_RANGES,
  AUDIT_RESULT_LABELS,
  AUDIT_SAVED_VIEWS,
  DEFAULT_AUDIT_FILTER,
  type AuditOrigin,
  type AuditRange,
  type AuditResult,
  type AuditSavedViewId,
} from "./audit-preview"
import {
  ANALYTICS_RANGES,
  DIMENSIONS,
  METRIC_KEYS,
  type AnalyticsRange,
  type Dimension,
  type MetricKey,
} from "./analytics-preview"
import {
  BUDGET_SCOPE_KINDS,
  BUDGET_WINDOWS,
  ENFORCEMENTS,
  type BudgetScopeKind,
  type BudgetWindow,
  type Enforcement,
} from "./budget-preview"

export type { DriftListState } from "./drift-preview"

function firstValue(value: unknown): string {
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.find((entry): entry is string => typeof entry === "string") ?? ""
  return ""
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

export const POLICY_EFFECT_FILTERS = Object.keys(POLICY_EFFECT_FILTER_LABELS) as PolicyEffectFilter[]
export const POLICY_MODE_FILTERS = Object.keys(POLICY_MODE_FILTER_LABELS) as PolicyModeFilter[]

export type PolicyListState = {
  snapshot: string
  q: string
  effect: PolicyEffectFilter
  mode: PolicyModeFilter
  scope: string
}

const SNAPSHOT_IDS = policySnapshots.map((snapshot) => snapshot.id)
export const POLICY_DEFAULT_SNAPSHOT = policySnapshots[0]?.id ?? ""

export function defaultPolicyListState(): PolicyListState {
  return {
    snapshot: POLICY_DEFAULT_SNAPSHOT,
    q: "",
    effect: "all",
    mode: "all",
    scope: "all",
  }
}

export function parsePolicyListQuery(query: Record<string, unknown>): PolicyListState {
  const state = defaultPolicyListState()
  const snapshot = firstValue(query.snapshot)
  if (snapshot && SNAPSHOT_IDS.includes(snapshot)) state.snapshot = snapshot
  state.q = firstValue(query.q).trim().slice(0, 120)
  const effect = firstValue(query.effect)
  if (allowed(effect, POLICY_EFFECT_FILTERS)) state.effect = effect
  const mode = firstValue(query.mode)
  if (allowed(mode, POLICY_MODE_FILTERS)) state.mode = mode
  const scope = firstValue(query.scope).trim().slice(0, 120)
  if (scope) state.scope = scope
  return state
}

export function serializePolicyListQuery(state: PolicyListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.snapshot !== POLICY_DEFAULT_SNAPSHOT) query.set("snapshot", state.snapshot)
  if (state.q.trim()) query.set("q", state.q.trim().slice(0, 120))
  if (state.effect !== "all") query.set("effect", state.effect)
  if (state.mode !== "all") query.set("mode", state.mode)
  if (state.scope !== "all") query.set("scope", state.scope)
  return query
}

export function policyListHref(state: PolicyListState): string {
  const query = serializePolicyListQuery(state).toString()
  return query ? `/policies?${query}` : "/policies"
}

export function policyListStateEqual(left: PolicyListState, right: PolicyListState): boolean {
  return serializePolicyListQuery(left).toString() === serializePolicyListQuery(right).toString()
}

export type PolicyRuleDetailState = {
  tab: PolicyRuleTab
  snapshot: string
}

export function parsePolicyRuleDetailQuery(query: Record<string, unknown>): PolicyRuleDetailState {
  const tab = firstValue(query.tab)
  const snapshot = firstValue(query.snapshot)
  return {
    tab: allowed(tab, POLICY_RULE_TABS.map((entry) => entry.id)) ? tab : "overview",
    snapshot: snapshot && SNAPSHOT_IDS.includes(snapshot) ? snapshot : POLICY_DEFAULT_SNAPSHOT,
  }
}

export function serializePolicyRuleDetailQuery(state: PolicyRuleDetailState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "overview") query.set("tab", state.tab)
  if (state.snapshot !== POLICY_DEFAULT_SNAPSHOT) query.set("snapshot", state.snapshot)
  return query
}

export const POLICY_TABS = ["rules", "decisions", "snapshots", "changes"] as const
export type PolicyTab = (typeof POLICY_TABS)[number]
export const POLICY_TAB_LABELS: Record<PolicyTab, string> = {
  rules: "Rules in force",
  decisions: "Decisions",
  snapshots: "Snapshots",
  changes: "Changes",
}

export const POLICY_DECISION_RANGES = ["7d", "30d"] as const
export type PolicyDecisionRange = (typeof POLICY_DECISION_RANGES)[number]
export const POLICY_DECISION_RANGE_LABELS: Record<PolicyDecisionRange, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
}

export const POLICY_RULE_SORTS = ["severity", "name"] as const
export type PolicyRuleSort = (typeof POLICY_RULE_SORTS)[number]
export const POLICY_RULE_SORT_LABELS: Record<PolicyRuleSort, string> = {
  severity: "Effect severity",
  name: "Name",
}

export type PolicyListStateV2 = {
  tab: PolicyTab
  snapshot: string
  q: string
  effect: PolicyEffectFilter
  mode: PolicyModeFilter
  area: PolicyArea | "all"
  changed: boolean
  sort: PolicyRuleSort
  decision: PolicyDecisionKind | "all"
  range: PolicyDecisionRange
}

export function defaultPolicyListStateV2(): PolicyListStateV2 {
  return {
    tab: "rules",
    snapshot: POLICY_DEFAULT_SNAPSHOT,
    q: "",
    effect: "all",
    mode: "all",
    area: "all",
    changed: false,
    sort: "severity",
    decision: "all",
    range: "7d",
  }
}

export function parsePolicyListQueryV2(query: Record<string, unknown>): PolicyListStateV2 {
  const state = defaultPolicyListStateV2()
  const tab = firstValue(query.tab)
  if (allowed(tab, POLICY_TABS)) state.tab = tab
  const snapshot = firstValue(query.snapshot)
  if (snapshot && SNAPSHOT_IDS.includes(snapshot)) state.snapshot = snapshot
  state.q = firstValue(query.q).trim().slice(0, 120)
  const effect = firstValue(query.effect)
  if (allowed(effect, POLICY_EFFECT_FILTERS)) state.effect = effect
  const mode = firstValue(query.mode)
  if (allowed(mode, POLICY_MODE_FILTERS)) state.mode = mode
  const area = firstValue(query.area)
  if (allowed(area, POLICY_AREA_ORDER)) state.area = area
  state.changed = firstValue(query.changed) === "1"
  const sort = firstValue(query.sort)
  if (allowed(sort, POLICY_RULE_SORTS)) state.sort = sort
  const decision = firstValue(query.decision)
  if (allowed(decision, POLICY_DECISION_ORDER)) state.decision = decision
  const range = firstValue(query.range)
  if (allowed(range, POLICY_DECISION_RANGES)) state.range = range
  return state
}

export function serializePolicyListQueryV2(state: PolicyListStateV2): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "rules") query.set("tab", state.tab)
  if (state.snapshot !== POLICY_DEFAULT_SNAPSHOT) query.set("snapshot", state.snapshot)
  if (state.q.trim()) query.set("q", state.q.trim().slice(0, 120))
  if (state.effect !== "all") query.set("effect", state.effect)
  if (state.mode !== "all") query.set("mode", state.mode)
  if (state.area !== "all") query.set("area", state.area)
  if (state.changed) query.set("changed", "1")
  if (state.sort !== "severity") query.set("sort", state.sort)
  if (state.decision !== "all") query.set("decision", state.decision)
  if (state.range !== "7d") query.set("range", state.range)
  return query
}

export function policyListHrefV2(state: PolicyListStateV2): string {
  const query = serializePolicyListQueryV2(state).toString()
  return query ? `/policies?${query}` : "/policies"
}

export const POLICY_SNAPSHOT_TABS = ["overview", "rules", "impact", "runs", "raw"] as const
export type PolicySnapshotTab = (typeof POLICY_SNAPSHOT_TABS)[number]
export const POLICY_SNAPSHOT_TAB_LABELS: Record<PolicySnapshotTab, string> = {
  overview: "Overview",
  rules: "Rules",
  impact: "Impact",
  runs: "Runs",
  raw: "Raw",
}

export type PolicySnapshotDetailState = {
  tab: PolicySnapshotTab
}

export function parsePolicySnapshotDetailQuery(query: Record<string, unknown>): PolicySnapshotDetailState {
  const tab = firstValue(query.tab)
  return { tab: allowed(tab, POLICY_SNAPSHOT_TABS) ? tab : "overview" }
}

export function serializePolicySnapshotDetailQuery(state: PolicySnapshotDetailState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "overview") query.set("tab", state.tab)
  return query
}

export function policySnapshotHref(snapshotId: string, state: PolicySnapshotDetailState = { tab: "overview" }): string {
  const query = serializePolicySnapshotDetailQuery(state).toString()
  return `/policies/snapshots/${encodeURIComponent(snapshotId)}${query ? `?${query}` : ""}`
}

export type PolicyCompareState = {
  from: string
  to: string
  hideUnchanged: boolean
}

export const POLICY_COMPARE_DEFAULT: PolicyCompareState = {
  from: policySnapshots[1]?.id ?? policySnapshots[0]?.id ?? "",
  to: policySnapshots[0]?.id ?? "",
  hideUnchanged: false,
}

export function parsePolicyCompareQuery(query: Record<string, unknown>): PolicyCompareState {
  const state = { ...POLICY_COMPARE_DEFAULT }
  const from = firstValue(query.from)
  const to = firstValue(query.to)
  if (from && SNAPSHOT_IDS.includes(from)) state.from = from
  if (to && SNAPSHOT_IDS.includes(to)) state.to = to
  state.hideUnchanged = firstValue(query.hideUnchanged) === "1"
  return state
}

export function serializePolicyCompareQuery(state: PolicyCompareState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.from !== POLICY_COMPARE_DEFAULT.from) query.set("from", state.from)
  if (state.to !== POLICY_COMPARE_DEFAULT.to) query.set("to", state.to)
  if (state.hideUnchanged) query.set("hideUnchanged", "1")
  return query
}

export function policyCompareHref(state: PolicyCompareState): string {
  const query = serializePolicyCompareQuery(state).toString()
  return query ? `/policies/compare?${query}` : "/policies/compare"
}

export function swapPolicyCompare(state: PolicyCompareState): PolicyCompareState {
  return { ...state, from: state.to, to: state.from }
}

export type PolicyRuleDetailStateV2 = {
  tab: PolicyRuleTab
  snapshot: string
  rev: number | null
}

export function parsePolicyRuleDetailQueryV2(query: Record<string, unknown>): PolicyRuleDetailStateV2 {
  const tab = firstValue(query.tab)
  const snapshot = firstValue(query.snapshot)
  const rawRevision = Number.parseInt(firstValue(query.rev), 10)
  return {
    tab: allowed(tab, POLICY_RULE_TABS.map((entry) => entry.id)) ? tab : "overview",
    snapshot: snapshot && SNAPSHOT_IDS.includes(snapshot) ? snapshot : POLICY_DEFAULT_SNAPSHOT,
    rev: Number.isInteger(rawRevision) && rawRevision >= 1 && rawRevision <= 999 ? rawRevision : null,
  }
}

export function serializePolicyRuleDetailQueryV2(state: PolicyRuleDetailStateV2): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "overview") query.set("tab", state.tab)
  if (state.snapshot !== POLICY_DEFAULT_SNAPSHOT) query.set("snapshot", state.snapshot)
  if (state.rev !== null) query.set("rev", String(state.rev))
  return query
}

export function policyRuleDetailHref(ruleId: string, state: PolicyRuleDetailStateV2): string {
  const query = serializePolicyRuleDetailQueryV2(state).toString()
  return `/policies/rules/${encodeURIComponent(ruleId)}${query ? `?${query}` : ""}`
}

export type PolicyResolveState = {
  run: string
  at: string
}

const RUN_ID_PATTERN = /^[A-Za-z0-9_-]{1,80}$/

export function parsePolicyResolveQuery(query: Record<string, unknown>): PolicyResolveState {
  const run = firstValue(query.run).trim()
  if (run && RUN_ID_PATTERN.test(run)) return { run, at: "" }
  const at = firstValue(query.at).trim().slice(0, 40)
  if (at && Number.isFinite(Date.parse(at))) return { run: "", at }
  return { run: "", at: "" }
}

export function serializePolicyResolveQuery(state: PolicyResolveState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.run) query.set("run", state.run)
  else if (state.at) query.set("at", state.at)
  return query
}

export function policyResolveHref(state: PolicyResolveState): string {
  const query = serializePolicyResolveQuery(state).toString()
  return query ? `/policies/resolve?${query}` : "/policies/resolve"
}

export const DRIFT_LIST_DEFAULT: DriftListState = {
  q: "",
  state: "active",
  severity: "all",
  owner: "all",
  agent: "all",
  sort: "severity",
  cause: "all",
}

export const DRIFT_STATE_FILTERS = ["active", "all", ...Object.keys(DRIFT_STATE_LABELS)] as const
export type DriftStateFilter = DriftState | "active" | "all"
export const DRIFT_SEVERITY_FILTERS = ["all", ...Object.keys(DRIFT_SEVERITY_LABELS)] as const
export const DRIFT_SORTS = ["severity", "opened", "change"] as const
export const DRIFT_SORT_LABELS: Record<DriftListState["sort"], string> = {
  severity: "Severity",
  opened: "Opened",
  change: "Change",
}
export const DRIFT_CAUSES = ["all", "recent"] as const

export function parseDriftListQuery(query: Record<string, unknown>): DriftListState {
  const state = { ...DRIFT_LIST_DEFAULT }
  state.q = firstValue(query.q).trim().slice(0, 120)
  const stateFilter = firstValue(query.state)
  if (allowed(stateFilter, DRIFT_STATE_FILTERS)) state.state = stateFilter as DriftStateFilter
  const severity = firstValue(query.severity)
  if (allowed(severity, DRIFT_SEVERITY_FILTERS)) state.severity = severity as DriftSeverity | "all"
  const owner = firstValue(query.owner).trim().slice(0, 80)
  if (owner) state.owner = owner
  const agent = firstValue(query.agent).trim().slice(0, 80)
  if (agent) state.agent = agent
  const sort = firstValue(query.sort)
  if (allowed(sort, DRIFT_SORTS)) state.sort = sort
  const cause = firstValue(query.cause)
  if (allowed(cause, DRIFT_CAUSES)) state.cause = cause
  return state
}

export function serializeDriftListQuery(state: DriftListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.q.trim()) query.set("q", state.q.trim().slice(0, 120))
  if (state.state !== DRIFT_LIST_DEFAULT.state) query.set("state", state.state)
  if (state.severity !== "all") query.set("severity", state.severity)
  if (state.owner !== "all") query.set("owner", state.owner)
  if (state.agent !== "all") query.set("agent", state.agent)
  if (state.sort !== DRIFT_LIST_DEFAULT.sort) query.set("sort", state.sort)
  if (state.cause !== "all") query.set("cause", state.cause)
  return query
}

export function driftListHref(state: DriftListState): string {
  const query = serializeDriftListQuery(state).toString()
  return query ? `/drift?${query}` : "/drift"
}

export const DRIFT_SIGNAL_TABS = ["overview", "runs", "compare", "activity"] as const
export type DriftSignalTab = (typeof DRIFT_SIGNAL_TABS)[number]
export const DRIFT_SIGNAL_TAB_LABELS: Record<DriftSignalTab, string> = {
  overview: "Overview",
  runs: "Runs",
  compare: "Compare",
  activity: "Activity",
}

export type DriftSignalDetailState = {
  tab: DriftSignalTab
}

export function parseDriftSignalDetailQuery(query: Record<string, unknown>): DriftSignalDetailState {
  const tab = firstValue(query.tab)
  return { tab: allowed(tab, DRIFT_SIGNAL_TABS) ? tab : "overview" }
}

export function serializeDriftSignalDetailQuery(state: DriftSignalDetailState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "overview") query.set("tab", state.tab)
  return query
}

export function driftSignalHref(signalId: string, state: DriftSignalDetailState = { tab: "overview" }): string {
  const query = serializeDriftSignalDetailQuery(state).toString()
  return `/drift/signals/${encodeURIComponent(signalId)}${query ? `?${query}` : ""}`
}

export const DRIFT_BASELINE_AGES = ["all", "stale", "expired"] as const
export type DriftBaselineAgeFilter = (typeof DRIFT_BASELINE_AGES)[number]
export const DRIFT_BASELINE_AGE_LABELS: Record<DriftBaselineAgeFilter, string> = {
  all: "Any age",
  stale: "Older than 30 days",
  expired: "Older than 90 days",
}

export type DriftBaselineListState = {
  agent: string
  age: DriftBaselineAgeFilter
}

export function parseDriftBaselineListQuery(query: Record<string, unknown>): DriftBaselineListState {
  const agent = firstValue(query.agent).trim().slice(0, 80)
  const age = firstValue(query.age)
  return {
    agent: agent || "all",
    age: allowed(age, DRIFT_BASELINE_AGES) ? age : "all",
  }
}

export function serializeDriftBaselineListQuery(state: DriftBaselineListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.agent !== "all") query.set("agent", state.agent)
  if (state.age !== "all") query.set("age", state.age)
  return query
}

export function driftBaselineListHref(state: DriftBaselineListState): string {
  const query = serializeDriftBaselineListQuery(state).toString()
  return query ? `/drift/baselines?${query}` : "/drift/baselines"
}

export function driftBaselineHref(agentId: string): string {
  return `/drift/baselines/${encodeURIComponent(agentId)}`
}

export const DRIFT_MONITOR_STATUS_FILTERS = ["all", "ok", "firing", "no_data", "muted"] as const
export type DriftMonitorStatusFilter = DriftMonitorStatus | "all"
export const DRIFT_MONITOR_STATUS_LABELS: Record<DriftMonitorStatusFilter, string> = {
  all: "Any status",
  ok: "OK",
  firing: "Firing",
  no_data: "No data",
  muted: "Muted",
}

export type DriftMonitorListState = {
  status: DriftMonitorStatusFilter
  agent: string
}

export function parseDriftMonitorListQuery(query: Record<string, unknown>): DriftMonitorListState {
  const status = firstValue(query.status)
  const agent = firstValue(query.agent).trim().slice(0, 80)
  return {
    status: allowed(status, DRIFT_MONITOR_STATUS_FILTERS) ? status : "all",
    agent: agent || "all",
  }
}

export function serializeDriftMonitorListQuery(state: DriftMonitorListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.status !== "all") query.set("status", state.status)
  if (state.agent !== "all") query.set("agent", state.agent)
  return query
}

export function driftMonitorListHref(state: DriftMonitorListState): string {
  const query = serializeDriftMonitorListQuery(state).toString()
  return query ? `/drift/monitors?${query}` : "/drift/monitors"
}

export type AuditListQueryState = {
  query: string
  view: AuditSavedViewId
  result: AuditResult | "all"
  origin: AuditOrigin | "all"
  range: AuditRange
  cursor: number | null
}

export const AUDIT_LIST_DEFAULT: AuditListQueryState = { ...DEFAULT_AUDIT_FILTER, query: "", cursor: null }

export function parseAuditListQuery(query: Record<string, unknown>): AuditListQueryState {
  const state = { ...AUDIT_LIST_DEFAULT }
  state.query = firstValue(query.q).trim().slice(0, 240)
  const view = firstValue(query.view)
  if (allowed(view, AUDIT_SAVED_VIEWS.map((entry) => entry.id))) state.view = view
  const result = firstValue(query.result)
  if (result === "all" || allowed(result, Object.keys(AUDIT_RESULT_LABELS))) {
    state.result = result as AuditResult | "all"
  }
  const origin = firstValue(query.origin)
  if (origin === "all" || allowed(origin, Object.keys(AUDIT_ORIGIN_LABELS))) {
    state.origin = origin as AuditOrigin | "all"
  }
  const range = firstValue(query.range)
  if (allowed(range, AUDIT_RANGES)) state.range = range
  const cursor = Number.parseInt(firstValue(query.cursor), 10)
  state.cursor = Number.isInteger(cursor) && cursor > 0 ? Math.min(cursor, 10_000) : null
  return state
}

export function serializeAuditListQuery(state: AuditListQueryState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.query.trim()) query.set("q", state.query.trim().slice(0, 240))
  if (state.view !== "all") query.set("view", state.view)
  if (state.result !== "all") query.set("result", state.result)
  if (state.origin !== "all") query.set("origin", state.origin)
  if (state.range !== "7d") query.set("range", state.range)
  if (state.cursor !== null) query.set("cursor", String(state.cursor))
  return query
}

export function auditListHref(state: AuditListQueryState): string {
  const query = serializeAuditListQuery(state).toString()
  return query ? `/audit?${query}` : "/audit"
}

export const AUDIT_EVENT_TABS = ["changes", "request", "related", "raw"] as const
export type AuditEventTab = (typeof AUDIT_EVENT_TABS)[number]
export const AUDIT_EVENT_TAB_LABELS: Record<AuditEventTab, string> = {
  changes: "Changes",
  request: "Request",
  related: "Related",
  raw: "Raw",
}

export type AuditEventDetailState = {
  tab: AuditEventTab
}

export function parseAuditEventDetailQuery(query: Record<string, unknown>): AuditEventDetailState {
  const tab = firstValue(query.tab)
  return { tab: allowed(tab, AUDIT_EVENT_TABS) ? tab : "changes" }
}

export function serializeAuditEventDetailQuery(state: AuditEventDetailState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== "changes") query.set("tab", state.tab)
  return query
}

export function auditEventHref(eventId: string, state: AuditEventDetailState = { tab: "changes" }): string {
  const query = serializeAuditEventDetailQuery(state).toString()
  return `/audit/events/${encodeURIComponent(eventId)}${query ? `?${query}` : ""}`
}

export type AuditObjectState = {
  actor: string
  action: string
  failed: boolean
}

export function parseAuditObjectQuery(query: Record<string, unknown>): AuditObjectState {
  return {
    actor: firstValue(query.actor).trim().slice(0, 80),
    action: firstValue(query.action).trim().slice(0, 80),
    failed: firstValue(query.failed) === "1",
  }
}

export function serializeAuditObjectQuery(state: AuditObjectState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.actor) query.set("actor", state.actor)
  if (state.action) query.set("action", state.action)
  if (state.failed) query.set("failed", "1")
  return query
}

export function auditObjectHistoryHref(
  type: string,
  id: string,
  state: AuditObjectState = { actor: "", action: "", failed: false },
): string {
  const query = serializeAuditObjectQuery(state).toString()
  return `/audit/objects/${encodeURIComponent(type)}/${encodeURIComponent(id)}${query ? `?${query}` : ""}`
}

export type AuditIntegrityState = {
  range: AuditRange
  format: (typeof AUDIT_EXPORT_FORMATS)[number]
}

export const AUDIT_INTEGRITY_DEFAULT: AuditIntegrityState = { range: "7d", format: "Signed NDJSON" }

export function parseAuditIntegrityQuery(query: Record<string, unknown>): AuditIntegrityState {
  const state = { ...AUDIT_INTEGRITY_DEFAULT }
  const range = firstValue(query.range)
  if (allowed(range, AUDIT_RANGES)) state.range = range
  const format = firstValue(query.format)
  if (allowed(format, AUDIT_EXPORT_FORMATS)) state.format = format
  return state
}

export function serializeAuditIntegrityQuery(state: AuditIntegrityState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.range !== "7d") query.set("range", state.range)
  if (state.format !== AUDIT_INTEGRITY_DEFAULT.format) query.set("format", state.format)
  return query
}

export function auditIntegrityHref(state: AuditIntegrityState): string {
  const query = serializeAuditIntegrityQuery(state).toString()
  return query ? `/audit/integrity?${query}` : "/audit/integrity"
}

/* ------------------------------------------------------------------ budgets */

export const BUDGET_TABS = ["reservations", "lifecycle"] as const
export type BudgetTab = (typeof BUDGET_TABS)[number]

export const BUDGET_TAB_LABELS: Record<BudgetTab, string> = {
  reservations: "Reservations",
  lifecycle: "Reservation lifecycle",
}

export type BudgetListState = {
  tab: BudgetTab
  window: BudgetWindow
  scope: BudgetScopeKind | "all"
  enforcement: Enforcement | "all"
  q: string
}

export const BUDGET_LIST_DEFAULT: BudgetListState = {
  tab: "reservations",
  window: "current",
  scope: "all",
  enforcement: "all",
  q: "",
}

export function parseBudgetQuery(query: Record<string, unknown>): BudgetListState {
  const state = { ...BUDGET_LIST_DEFAULT }
  const tab = firstValue(query.tab)
  if (allowed(tab, BUDGET_TABS)) state.tab = tab
  const window = firstValue(query.window)
  if (allowed(window, BUDGET_WINDOWS)) state.window = window
  const scope = firstValue(query.scope)
  if (scope === "all" || allowed(scope, BUDGET_SCOPE_KINDS)) state.scope = scope as BudgetScopeKind | "all"
  const enforcement = firstValue(query.enforcement)
  if (enforcement === "all" || allowed(enforcement, ENFORCEMENTS)) state.enforcement = enforcement as Enforcement | "all"
  state.q = firstValue(query.q).trim().slice(0, 120)
  return state
}

export function serializeBudgetQuery(state: BudgetListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== BUDGET_LIST_DEFAULT.tab) query.set("tab", state.tab)
  if (state.window !== BUDGET_LIST_DEFAULT.window) query.set("window", state.window)
  if (state.scope !== "all") query.set("scope", state.scope)
  if (state.enforcement !== "all") query.set("enforcement", state.enforcement)
  if (state.q.trim()) query.set("q", state.q.trim())
  return query
}

export function budgetHref(state: BudgetListState): string {
  const query = serializeBudgetQuery(state).toString()
  return query ? `/budgets?${query}` : "/budgets"
}

/* ----------------------------------------------------------------- analytics */

export const ANALYTICS_TABS = ["usage", "latency", "breakdown"] as const
export type AnalyticsTab = (typeof ANALYTICS_TABS)[number]

export const ANALYTICS_TAB_LABELS: Record<AnalyticsTab, string> = {
  usage: "Usage",
  latency: "Latency",
  breakdown: "By dimension",
}

export type AnalyticsListState = {
  tab: AnalyticsTab
  range: AnalyticsRange
  metric: MetricKey
  dimension: Dimension
  asTable: boolean
}

export const ANALYTICS_LIST_DEFAULT: AnalyticsListState = {
  tab: "usage",
  range: "14d",
  metric: "spendUsd",
  dimension: "provider",
  asTable: false,
}

export function parseAnalyticsQuery(query: Record<string, unknown>): AnalyticsListState {
  const state = { ...ANALYTICS_LIST_DEFAULT }
  const tab = firstValue(query.tab)
  if (allowed(tab, ANALYTICS_TABS)) state.tab = tab
  const range = firstValue(query.range)
  if (allowed(range, ANALYTICS_RANGES)) state.range = range
  const metric = firstValue(query.metric)
  if (allowed(metric, METRIC_KEYS)) state.metric = metric
  const dimension = firstValue(query.dimension)
  if (allowed(dimension, DIMENSIONS)) state.dimension = dimension
  state.asTable = firstValue(query.view) === "table"
  return state
}

export function serializeAnalyticsQuery(state: AnalyticsListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== ANALYTICS_LIST_DEFAULT.tab) query.set("tab", state.tab)
  if (state.range !== ANALYTICS_LIST_DEFAULT.range) query.set("range", state.range)
  if (state.metric !== ANALYTICS_LIST_DEFAULT.metric) query.set("metric", state.metric)
  if (state.dimension !== ANALYTICS_LIST_DEFAULT.dimension) query.set("dimension", state.dimension)
  if (state.asTable) query.set("view", "table")
  return query
}

export function analyticsHref(state: AnalyticsListState): string {
  const query = serializeAnalyticsQuery(state).toString()
  return query ? `/analytics?${query}` : "/analytics"
}

/* ------------------------------------------------------------------ explore */

/**
 * The four span lenses. Each one re-reads the same span rows; none of them adds data,
 * so the choice is presentation state and belongs in the URL like every other view choice.
 */
export const EXPLORE_LENSES = ["waterfall", "tree", "list", "map"] as const
export type ExploreLens = (typeof EXPLORE_LENSES)[number]

export const EXPLORE_LENS_LABELS: Record<ExploreLens, string> = {
  waterfall: "Waterfall",
  tree: "Tree",
  list: "List",
  map: "Map",
}

export const EXPLORE_LENS_MEANING: Record<ExploreLens, string> = {
  waterfall: "Each span positioned on the run's own timeline, so overlap and gaps are visible.",
  tree: "Spans nested under their parent, so the call structure is visible without reading ids.",
  list: "Every span as a row, so ids and timings can be copied exactly.",
  map: "Spans as cards with their parent, so the shape of the graph is visible at a glance.",
}

/** Inspector sections for a single run. */
export const EXPLORE_RUN_TABS = ["overview", "timeline", "evidence", "assembly", "tools", "raw"] as const
export type ExploreRunTab = (typeof EXPLORE_RUN_TABS)[number]

export const EXPLORE_RUN_TAB_LABELS: Record<ExploreRunTab, string> = {
  overview: "Overview",
  timeline: "Timeline",
  evidence: "Evidence",
  assembly: "Assembly",
  tools: "Tools",
  raw: "Raw",
}

export const EXPLORE_RUN_TAB_MEANING: Record<ExploreRunTab, string> = {
  overview: "Identity, timing and the sections this run did not return.",
  timeline: "The span rows this run returned, in whichever arrangement is easiest to read.",
  evidence: "The evidence row behind the run: completeness, publication, freshness, retention and watermark.",
  assembly: "Context assembly stage timings, retrieval candidates and the directive version applied.",
  tools: "Tool calls recorded for the run, with their status and error codes.",
  raw: "The validated detail payload exactly as the contract returned it.",
}

export type ExploreRunState = {
  tab: ExploreRunTab
  lens: ExploreLens
}

export const EXPLORE_RUN_DEFAULT: ExploreRunState = { tab: "overview", lens: "waterfall" }

export function parseExploreRunQuery(query: Record<string, unknown>): ExploreRunState {
  const state = { ...EXPLORE_RUN_DEFAULT }
  const tab = firstValue(query.tab)
  if (allowed(tab, EXPLORE_RUN_TABS)) state.tab = tab
  const lens = firstValue(query.lens)
  if (allowed(lens, EXPLORE_LENSES)) state.lens = lens
  return state
}

export function serializeExploreRunQuery(state: ExploreRunState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== EXPLORE_RUN_DEFAULT.tab) query.set("tab", state.tab)
  if (state.lens !== EXPLORE_RUN_DEFAULT.lens) query.set("lens", state.lens)
  return query
}

/** The run page keeps the caller's `return` target so the back link survives view changes. */
export function exploreRunHref(runId: string, state: ExploreRunState, returnTo: string): string {
  const query = serializeExploreRunQuery(state)
  query.set("return", returnTo)
  return `/explore/r/${encodeURIComponent(runId)}?${query.toString()}`
}

/** Client-side filter over the runs already returned for one trace. */
export const EXPLORE_TRACE_STATUSES = ["all", "ok", "error"] as const
export type ExploreTraceStatus = (typeof EXPLORE_TRACE_STATUSES)[number]

export const EXPLORE_TRACE_STATUS_LABELS: Record<ExploreTraceStatus, string> = {
  all: "All runs",
  ok: "Completed",
  error: "Failed",
}

export type ExploreTraceState = {
  status: ExploreTraceStatus
}

export const EXPLORE_TRACE_DEFAULT: ExploreTraceState = { status: "all" }

export function parseExploreTraceQuery(query: Record<string, unknown>): ExploreTraceState {
  const status = firstValue(query.status)
  return { status: allowed(status, EXPLORE_TRACE_STATUSES) ? status : "all" }
}

export function serializeExploreTraceQuery(state: ExploreTraceState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.status !== EXPLORE_TRACE_DEFAULT.status) query.set("status", state.status)
  return query
}

export function exploreTraceHref(traceId: string, state: ExploreTraceState, returnTo: string): string {
  const query = serializeExploreTraceQuery(state)
  query.set("return", returnTo)
  const text = query.toString()
  return `/explore/t/${encodeURIComponent(traceId)}${text ? `?${text}` : ""}`
}

/* ------------------------------------------------------------------ overview */

export const OVERVIEW_TABS = ["attention", "runs", "sources"] as const
export type OverviewTab = (typeof OVERVIEW_TABS)[number]

export const OVERVIEW_TAB_LABELS: Record<OverviewTab, string> = {
  attention: "Needs attention",
  runs: "Recent runs",
  sources: "Sources and session",
}

export const OVERVIEW_TAB_MEANING: Record<OverviewTab, string> = {
  attention: "Every open finding this page can derive from a value the platform actually reported.",
  runs: "The newest run metadata this organization returned — five rows, no query, no inference.",
  sources: "Which contract each figure came from, whether it resolved, and when it was read.",
}

export type OverviewState = {
  tab: OverviewTab
}

export const OVERVIEW_DEFAULT: OverviewState = { tab: "attention" }

export function parseOverviewQuery(query: Record<string, unknown>): OverviewState {
  const tab = firstValue(query.tab)
  return { tab: allowed(tab, OVERVIEW_TABS) ? tab : "attention" }
}

export function serializeOverviewQuery(state: OverviewState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== OVERVIEW_DEFAULT.tab) query.set("tab", state.tab)
  return query
}

export function overviewHref(state: OverviewState): string {
  const query = serializeOverviewQuery(state).toString()
  return query ? `/?${query}` : "/"
}

/* ------------------------------------------------------------------ platform */

export const PLATFORM_TABS = ["dependencies", "pipeline", "recovery", "raw"] as const
export type PlatformTab = (typeof PLATFORM_TABS)[number]

export const PLATFORM_TAB_LABELS: Record<PlatformTab, string> = {
  dependencies: "Dependency ledger",
  pipeline: "Ingestion and outbox",
  recovery: "Recovery and deployment",
  raw: "Snapshot payload",
}

export const PLATFORM_TAB_MEANING: Record<PlatformTab, string> = {
  dependencies: "One row per dependency the platform checked in this snapshot, sorted by how broken it is.",
  pipeline: "Lag, dead-letter depth and the outbox watermark, plus the history that is not connected.",
  recovery: "Backup, restore drill, retention horizon and the deployed image digest.",
  raw: "The validated snapshot object, so a claim on this page can be checked against the payload itself.",
}

export type PlatformState = {
  tab: PlatformTab
}

export const PLATFORM_DEFAULT: PlatformState = { tab: "dependencies" }

export function parsePlatformQuery(query: Record<string, unknown>): PlatformState {
  const tab = firstValue(query.tab)
  return { tab: allowed(tab, PLATFORM_TABS) ? tab : "dependencies" }
}

export function serializePlatformQuery(state: PlatformState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.tab !== PLATFORM_DEFAULT.tab) query.set("tab", state.tab)
  return query
}

export function platformHref(state: PlatformState): string {
  const query = serializePlatformQuery(state).toString()
  return query ? `/platform?${query}` : "/platform"
}
