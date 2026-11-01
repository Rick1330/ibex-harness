import type {
  PublicOperatorContext,
  PublicOperatorOverview,
  PublicOperatorTraceList,
  PublicPlatformHealth,
} from "~~/shared/operator/public"
import {
  platformDependencyCounts,
  platformDependencyEntries,
  platformDependencyName,
  platformDependencyStatusLabel,
  PLATFORM_STALE_AFTER_SECONDS,
} from "@/lib/platform-readiness"
import { GOVERN_SEVERITY_ORDER, severityForDependency, type GovernSeverity } from "@/lib/govern-severity"
import { exploreAttention } from "@/lib/explore-view"
import { liveStaleness } from "@/lib/live-format"
import { formatGovernNumber, formatGovernStamp, formatGovernStampSeconds } from "@/lib/govern-format"

/**
 * View model for the Overview surface.
 *
 * Overview is one of two live surfaces, so every value here is derived from a field that
 * `operator.overview.v1`, `operator.platform.health.v1` or `operator.trace-list.v1` actually
 * returned. A figure with no field behind it stays unreported; it is never estimated, and an
 * attention row is only raised for a state the platform itself recorded.
 */

/** The five newest rows the landing page reads. Anything wider is Explore's job. */
export const OVERVIEW_RUNS_LIMIT = 5

export const OVERVIEW_CONTRACT = "operator.overview.v1 + operator.platform.health.v1"

export const OVERVIEW_TRACE_CONTRACT = "operator.trace-list.v1"

export type OverviewSourceId = "context" | "overview" | "health" | "traces"
export type OverviewSourceState = "ok" | "degraded" | "missing" | "pending"

export type OverviewSourceRow = {
  id: OverviewSourceId
  label: string
  contract: string
  state: OverviewSourceState
  observedAt: string | null
  /** What on this page would disappear if this source stopped resolving. */
  feeds: string
  detail: string
}

export const OVERVIEW_SOURCE_STATE_LABELS: Record<OverviewSourceState, string> = {
  ok: "Read",
  degraded: "Partial",
  missing: "Not read",
  pending: "Reading",
}

export type OverviewAttentionRow = {
  id: string
  severity: GovernSeverity
  title: string
  detail: string
  /** The contract that produced the value, so the finding can be re-checked. */
  origin: string
  link: { label: string; href: string } | null
}

export type OverviewFlags = {
  hasOverview: boolean
  hasHealth: boolean
  hasTraces: boolean
  authIssue: boolean
  loading: boolean
}

export type OverviewStaleness = {
  ageSeconds: number | null
  stale: boolean
  label: string
  asSpan: string
}

const DEPENDENCY_HREF = "/platform"
const RUNS_HREF = "/explore"

function present(value: PublicPlatformHealth | null | undefined): PublicPlatformHealth | null {
  return value ?? null
}

function reported(value: string | null): string {
  return value ? formatGovernStamp(value) : "not recorded"
}

/** Relative age measured against the caller's clock, because this page reads live data. */
export function overviewStaleness(observedAt: string | null, nowMs: number | null): OverviewStaleness {
  return liveStaleness(observedAt, nowMs, PLATFORM_STALE_AFTER_SECONDS)
}

export function buildOverviewSources(input: {
  context: PublicOperatorContext | null
  overview: PublicOperatorOverview | null
  health: PublicPlatformHealth | null
  traces: PublicOperatorTraceList | null
  healthFailed: boolean
  tracesFailed: boolean
  loading: boolean
}): OverviewSourceRow[] {
  const state = (resolved: boolean, failed: boolean): OverviewSourceState =>
    resolved ? "ok" : failed ? "degraded" : input.loading ? "pending" : "missing"

  return [
    {
      id: "context",
      label: "Session context",
      contract: "operator.context.v1",
      state: input.context ? "ok" : input.loading ? "pending" : "missing",
      observedAt: input.context?.observed_at ?? null,
      feeds: "Organization name, role and the read-only statement in the header.",
      detail: input.context
        ? `Verified for ${input.context.org_slug} as ${input.context.role ?? "an unreported role"}.`
        : "The operator session was not verified, so no identity-dependent claim is made on this page.",
    },
    {
      id: "overview",
      label: "Organization snapshot",
      contract: "operator.overview.v1",
      state: state(Boolean(input.overview), false),
      observedAt: input.overview?.observed_at ?? null,
      feeds: "The active-user, agent and active-agent tiles.",
      detail: input.overview
        ? `Reported complete by the source: the contract only resolves with completeness="complete".`
        : "No organization counts were returned, so the tiles stay unreported rather than showing zero.",
    },
    {
      id: "health",
      label: "Platform health",
      contract: "operator.platform.health.v1",
      state: input.health ? (input.healthFailed ? "degraded" : "ok") : state(false, input.healthFailed),
      observedAt: input.health?.observed_at ?? null,
      feeds: "The dependency count, the verdict, and every platform attention row.",
      detail: input.health
        ? platformDependencyEntries(input.health).length
          ? "Current snapshot; history and SLOs are separate contracts and are not read here."
          : "The snapshot resolved but reported no dependency checks. An empty report is not a healthy report."
        : "Dependency health was not read, so the verdict stays open instead of assuming healthy.",
    },
    {
      id: "traces",
      label: "Run metadata",
      contract: OVERVIEW_TRACE_CONTRACT,
      state: input.traces ? (input.tracesFailed ? "degraded" : "ok") : state(false, input.tracesFailed),
      observedAt: input.traces?.observed_at ?? null,
      feeds: `The ${OVERVIEW_RUNS_LIMIT} rows on the Recent runs tab and the run-derived attention rows.`,
      detail: input.traces
        ? `${formatGovernNumber(input.traces.returned_count)} rows returned; a count of the organization is only claimed when the source reports a matched total.`
        : "Run metadata was not read, so the Recent runs tab has no rows to show.",
    },
  ]
}

/**
 * Every open finding the live sources support, ordered by severity then by origin.
 *
 * Rows are only raised from a value the platform wrote: a dependency status, the degraded-mode
 * flag, a queue depth, a null recovery field, or the evidence state of the run rows themselves.
 */
export function buildOverviewAttention(input: {
  health: PublicPlatformHealth | null
  traces: PublicOperatorTraceList | null
  staleness: OverviewStaleness
  healthFailed: boolean
  tracesFailed: boolean
}): OverviewAttentionRow[] {
  const rows: OverviewAttentionRow[] = []
  const health = present(input.health)
  const traces = input.traces

  if (health) {
    const entries = platformDependencyEntries(health)
    for (const [name, status] of entries) {
      const severity = severityForDependency(status)
      if (!severity) continue
      rows.push({
        id: `dependency:${name}`,
        severity,
        title: `${platformDependencyName(name)} reported ${platformDependencyStatusLabel(status).toLowerCase()}`,
        detail: `The platform's own dependency check returned "${status}" in the snapshot read ${reported(health.observed_at)}.`,
        origin: "operator.platform.health.v1",
        link: { label: "Open Platform", href: DEPENDENCY_HREF },
      })
    }

    if (health.degraded_mode) {
      rows.push({
        id: "degraded-mode",
        severity: "warning",
        title: "Platform is serving in degraded mode",
        detail: "The snapshot sets degraded_mode even where every dependency reports ok, so the mode is reported separately from the checks.",
        origin: "operator.platform.health.v1",
        link: { label: "Open Platform", href: DEPENDENCY_HREF },
      })
    }

    if (health.dlq_depth !== null && health.dlq_depth > 0) {
      rows.push({
        id: "dlq",
        severity: "warning",
        title: `${formatGovernNumber(health.dlq_depth)} item${health.dlq_depth === 1 ? "" : "s"} in the dead-letter queue`,
        detail: "Depth is what the platform reports for the queue; the items themselves and their failure reasons are not part of this contract.",
        origin: "operator.platform.health.v1",
        link: { label: "Open ingestion", href: "/platform?tab=pipeline" },
      })
    }

    const unrecorded = [
      health.last_backup_at === null ? "last backup" : null,
      health.last_restore_drill === null ? "restore drill" : null,
      health.deploy_image_digest === null ? "deployed image digest" : null,
      health.outbox_max_aggregate_seq === null ? "outbox watermark" : null,
    ].filter((label): label is string => label !== null)

    if (unrecorded.length) {
      rows.push({
        id: "recovery-unrecorded",
        severity: "info",
        title: `Recovery and chain evidence not recorded: ${unrecorded.join(", ")}`,
        detail: "The snapshot returned null for these fields. Absence is reported as absence; nothing is filled in from an earlier snapshot.",
        origin: "operator.platform.health.v1",
        link: { label: "Open recovery", href: "/platform?tab=recovery" },
      })
    }
  }

  if (input.staleness.stale) {
    rows.push({
      id: "stale-snapshot",
      severity: "warning",
      title: `Platform snapshot is ${input.staleness.asSpan}`,
      detail: `The page marks a snapshot stale after ${PLATFORM_STALE_AFTER_SECONDS / 60} minutes. Values below still describe the last observation, not the present.`,
      origin: "operator.platform.health.v1",
      link: { label: "Re-read", href: DEPENDENCY_HREF },
    })
  }

  if (traces) {
    const attention = exploreAttention(traces.items)
    const scope = `${traces.items.length} run${traces.items.length === 1 ? "" : "s"} on this page`

    if (attention.errors > 0) {
      rows.push({
        id: "runs-failed",
        severity: "warning",
        title: `${attention.errors} of ${scope} reported an error`,
        detail: "Status comes from the proxy's own record of each run. It says nothing about runs that are not on this page.",
        origin: OVERVIEW_TRACE_CONTRACT,
        link: { label: "Open Explore", href: `${RUNS_HREF}?status=error` },
      })
    }

    if (attention.brokenPublication > 0) {
      rows.push({
        id: "runs-publication",
        severity: "warning",
        title: `${attention.brokenPublication} of ${scope} have a broken evidence publication`,
        detail: "Publication failed, was poisoned, or could not be read. The run happened; the trail behind it may not exist downstream.",
        origin: OVERVIEW_TRACE_CONTRACT,
        link: { label: "Open Explore", href: RUNS_HREF },
      })
    }

    if (attention.incomplete > 0) {
      rows.push({
        id: "runs-incomplete",
        severity: "info",
        title: `${attention.incomplete} of ${scope} recorded an incomplete record`,
        detail: "Completeness is partial, late, redacted, expired or deleted. Each row keeps the code the source reported so the reason can be read on the run.",
        origin: OVERVIEW_TRACE_CONTRACT,
        link: { label: "Open Explore", href: `${RUNS_HREF}?completeness=partial` },
      })
    }

    if (attention.sampled > 0) {
      rows.push({
        id: "runs-sampled",
        severity: "info",
        title: `${attention.sampled} of ${scope} were sampled captures`,
        detail: "For a sampled run, missing spans are expected and are not evidence of a gap in the platform.",
        origin: OVERVIEW_TRACE_CONTRACT,
        link: { label: "Open Explore", href: `${RUNS_HREF}?completeness=sampled` },
      })
    }

    if (traces.truncated && traces.matched_count === null) {
      rows.push({
        id: "runs-scope",
        severity: "info",
        title: "Run totals on this page describe a page, not the organization",
        detail: "The list was truncated and the source reported no matched total, so no count here can be read as a count of all runs.",
        origin: OVERVIEW_TRACE_CONTRACT,
        link: { label: "Open Explore", href: RUNS_HREF },
      })
    }
  }

  if (input.healthFailed && !health) {
    rows.push({
      id: "health-unread",
      severity: "warning",
      title: "Platform health could not be read",
      detail: "Without the health snapshot the organization verdict cannot be closed, and no dependency, queue or recovery claim is made.",
      origin: "operator.platform.health.v1",
      link: { label: "Open Platform", href: DEPENDENCY_HREF },
    })
  }

  if (input.tracesFailed && !traces) {
    rows.push({
      id: "traces-unread",
      severity: "warning",
      title: "Run metadata could not be read",
      detail: "The Recent runs tab stays empty. Absent metadata is reported as absent; no earlier page is reused.",
      origin: OVERVIEW_TRACE_CONTRACT,
      link: { label: "Open Explore", href: RUNS_HREF },
    })
  }

  return rows.sort(
    (left, right) =>
      GOVERN_SEVERITY_ORDER[left.severity] - GOVERN_SEVERITY_ORDER[right.severity] ||
      left.origin.localeCompare(right.origin) ||
      left.title.localeCompare(right.title),
  )
}

export type OverviewVerdict = {
  tone: "ok" | "warning" | "muted"
  text: string
  caveat: string | null
  caveatDetail: string | null
}

/** One sentence an operator can act on, with the reason it is not stronger than that. */
export function overviewVerdict(input: {
  flags: OverviewFlags
  issues: OverviewAttentionRow[]
  health: PublicPlatformHealth | null
  staleness: OverviewStaleness
}): OverviewVerdict {
  const { flags } = input

  if (flags.authIssue) {
    return {
      tone: "muted",
      text: "Sign in to read this organization.",
      caveat: "Nothing on this page is substituted from preview data.",
      caveatDetail:
        "The overview, the health snapshot and the run list are all tenant-scoped reads behind the operator session. Without it the console has no values to report, and it shows none.",
    }
  }

  if (flags.loading && !flags.hasOverview) {
    return {
      tone: "muted",
      text: "Reading the organization snapshot.",
      caveat: null,
      caveatDetail: null,
    }
  }

  if (!flags.hasOverview) {
    return {
      tone: "warning",
      text: "Organization snapshot unavailable.",
      caveat: "No counts are invented for the gap.",
      caveatDetail:
        "operator.overview.v1 did not resolve for this session. The tiles stay unreported and the verdict stays open rather than falling back to a sample organization.",
    }
  }

  const critical = input.issues.filter((row) => row.severity === "critical").length
  const warning = input.issues.filter((row) => row.severity === "warning").length

  if (!flags.hasHealth) {
    return {
      tone: "muted",
      text: "Organization counts are read; platform health is not.",
      caveat: "Verdict stays open",
      caveatDetail:
        "Counts and dependency health are separate contracts. A healthy organization cannot be claimed while operator.platform.health.v1 has not resolved.",
    }
  }

  if (critical > 0) {
    return {
      tone: "warning",
      text: `${critical} critical finding${critical === 1 ? "" : "s"} and ${warning} warning${warning === 1 ? "" : "s"} are open on this snapshot.`,
      caveat: input.staleness.stale ? `Snapshot is ${input.staleness.asSpan}` : null,
      caveatDetail:
        "Every finding is derived from a value the platform reported in this snapshot. Findings do not survive a new read unless the same field still reports them.",
    }
  }

  if (warning > 0 || input.issues.length > 0) {
    return {
      tone: warning > 0 ? "warning" : "muted",
      text: `${input.issues.length} reported finding${input.issues.length === 1 ? "" : "s"}; none is critical.`,
      caveat: input.staleness.stale ? `Snapshot is ${input.staleness.asSpan}` : null,
      caveatDetail:
        "These are observations from the current snapshot. Incidents, SLO history and evidence coverage have their own contracts and are not connected to this verdict.",
    }
  }

  return {
    tone: "ok",
    text: `No reported issues across ${formatGovernNumber(platformDependencyCounts(platformDependencyEntries(input.health)).total)} dependencies.`,
    caveat: "Observation, not certification",
    caveatDetail:
      "Every dependency in this snapshot reports ok and no other field is out of order. That is an observation at one point in time with no evidence record behind it: it does not certify coverage, availability over a window, or that the snapshot is still true now.",
  }
}

export type OverviewTile = {
  label: string
  value: string
  helper: string | null
  tone: "default" | "warning" | "critical" | "success"
}

/** Only quantities belong in tiles — words like "active" or "degraded" are read in the status line. */
export function overviewTiles(input: {
  overview: PublicOperatorOverview | null
  health: PublicPlatformHealth | null
  traces: PublicOperatorTraceList | null
}): OverviewTile[] {
  const counts = input.overview?.counts ?? null
  const dependencyCounts = platformDependencyCounts(platformDependencyEntries(input.health))

  return [
    {
      label: "Agents in this organization",
      value: counts ? formatGovernNumber(counts.agents) : "Not reported",
      helper: counts
        ? `${formatGovernNumber(counts.active_agents)} reported active · source operator.overview.v1`
        : "The organization snapshot did not resolve.",
      tone: "default",
    },
    {
      label: "Active users",
      value: counts ? formatGovernNumber(counts.active_users) : "Not reported",
      helper: counts ? "Verified accounts reported by the source." : null,
      tone: "default",
    },
    {
      label: "Dependencies reporting ok",
      value: input.health ? `${formatGovernNumber(dependencyCounts.ok)} of ${formatGovernNumber(dependencyCounts.total)}` : "Not reported",
      helper: input.health
        ? `${formatGovernNumber(dependencyCounts.degraded)} degraded · ${formatGovernNumber(dependencyCounts.unavailable)} unavailable`
        : "operator.platform.health.v1 did not resolve.",
      tone: dependencyCounts.unavailable > 0 ? "critical" : dependencyCounts.degraded > 0 ? "warning" : "default",
    },
    {
      label: "Runs read for this page",
      value: input.traces ? formatGovernNumber(input.traces.returned_count) : "Not reported",
      helper: input.traces
        ? input.traces.matched_count === null
          ? "No matched total reported by the source."
          : `${formatGovernNumber(input.traces.matched_count)} matched the query.`
        : "Run metadata did not resolve.",
      tone: "default",
    },
  ]
}

/** Absolute stamps for the footer of the runs panel: relative in cells, absolute on hover. */
export function overviewRunsWindow(traces: PublicOperatorTraceList | null): string {
  if (!traces) return "No window observed."
  return `Query window ${formatGovernStampSeconds(traces.query_start)} → ${formatGovernStampSeconds(traces.query_end)}`
}

export const OVERVIEW_NOTES: { lead: string; body: string }[] = [
  {
    lead: "This page is a summary of three reads, not a fourth data source.",
    body: "Every figure comes from operator.overview.v1, operator.platform.health.v1 or the five run rows taken from operator.trace-list.v1. Nothing here is computed across sources except the finding list, which only restates what each source already reported.",
  },
  {
    lead: "Counts describe what was returned, not what exists.",
    body: "The run tile counts rows on this page. A matched total is shown only when the list contract reports one; a truncated page without a matched total is labelled as such.",
  },
  {
    lead: "Health is an observation, and it goes stale.",
    body: `A snapshot older than ${PLATFORM_STALE_AFTER_SECONDS / 60} minutes is marked stale and its findings stay on the list with that caveat. The page never blends an old snapshot into a new one.`,
  },
  {
    lead: "Certification is a separate claim.",
    body: "Evidence coverage is not connected to this surface, so it is shown as pending with the contract it needs rather than inferred from a healthy dependency list.",
  },
]
