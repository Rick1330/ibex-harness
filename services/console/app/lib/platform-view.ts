import type { PublicPlatformHealth } from "~~/shared/operator/public"
import {
  PLATFORM_STALE_AFTER_SECONDS,
  platformDependencyCounts,
  platformDependencyEntries,
  platformDependencyName,
  platformDependencyStatusLabel,
  sortPlatformDependencies,
  type PlatformDependencyStatus,
  type PlatformReadinessState,
} from "@/lib/platform-readiness"
import { severityForDependency, type GovernSeverity } from "@/lib/govern-severity"
import { formatLiveRelative, liveStaleness, type LiveStaleness } from "@/lib/live-format"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import { formatSeconds } from "@/lib/format"

/**
 * View model for the Platform surface.
 *
 * Platform reads one live contract, `operator.platform.health.v1`, and nothing else. Every value
 * below is either a field that snapshot carried or an explicit "not reported" — the page has no
 * history, no incident feed and no SLO series, and it never draws one.
 */

export const PLATFORM_CONTRACT = "operator.platform.health.v1"

/** What each dependency status means in the platform's own words, so a row can be read without a legend. */
export const DEPENDENCY_STATUS_MEANING: Record<PlatformDependencyStatus, string> = {
  ok: "The platform's own check passed when this snapshot was taken.",
  degraded: "The check completed with a problem: reachable, but not serving normally.",
  unavailable: "The check did not pass. The platform reports the dependency as not reachable.",
}

export type PlatformDependencyRow = {
  code: string
  label: string
  status: PlatformDependencyStatus
  statusLabel: string
  /** Severity only exists when the status is a finding; `ok` produces none. */
  severity: GovernSeverity | null
  meaning: string
}

export function platformDependencyRows(health: PublicPlatformHealth | null): PlatformDependencyRow[] {
  return sortPlatformDependencies(platformDependencyEntries(health)).map(([code, status]) => ({
    code,
    label: platformDependencyName(code),
    status,
    statusLabel: platformDependencyStatusLabel(status),
    severity: severityForDependency(status),
    meaning: DEPENDENCY_STATUS_MEANING[status],
  }))
}

export function platformStaleness(observedAt: string | null, nowMs: number | null): LiveStaleness {
  return liveStaleness(observedAt, nowMs, PLATFORM_STALE_AFTER_SECONDS)
}

export type PlatformVerdict = {
  tone: "ok" | "warning" | "muted"
  text: string
  caveat: string | null
  caveatDetail: string | null
}

export function platformVerdict(input: {
  health: PublicPlatformHealth | null
  readiness: PlatformReadinessState
  staleness: LiveStaleness
  failureDetail: string | null
}): PlatformVerdict {
  const { readiness, staleness } = input

  if (readiness === "auth") {
    return {
      tone: "muted",
      text: "Sign in to read platform health.",
      caveat: "Nothing is substituted for an unverified session",
      caveatDetail:
        "The snapshot is a tenant-scoped operator read. Without a session that allows platform reads the console has no values, and it shows none rather than a sample report.",
    }
  }

  if (readiness === "loading") {
    return { tone: "muted", text: "Reading the platform snapshot.", caveat: null, caveatDetail: null }
  }

  if (!input.health) {
    return {
      tone: "warning",
      text: "Platform snapshot unavailable.",
      caveat: "No values are inferred for the gap",
      caveatDetail: `${input.failureDetail ?? "The health read did not resolve."} Dependency status, queue depth, recovery evidence and the deployed digest all stay unreported until a snapshot resolves.`,
    }
  }

  if (readiness === "no-checks") {
    return {
      tone: "warning",
      text: "The snapshot resolved but reported no dependency checks.",
      caveat: "An empty report is not a healthy report",
      caveatDetail:
        "dependency_health came back empty. The page reads that as an absence of evidence, not as evidence of absence: no dependency has been shown to work.",
    }
  }

  const counts = platformDependencyCounts(platformDependencyEntries(input.health))
  const findings = counts.degraded + counts.unavailable

  if (readiness === "blocked") {
    return {
      tone: "warning",
      text: `${counts.unavailable} of ${counts.total} dependencies are reported unavailable.`,
      caveat: staleness.stale ? `Snapshot is ${staleness.asSpan}` : "Read once, at one moment",
      caveatDetail:
        "An unavailable dependency is the platform's own failed check. This page cannot say which requests were affected, because the run and incident contracts are not connected here.",
    }
  }

  if (readiness === "degraded") {
    const mode = input.health.degraded_mode ? " and the platform reports serving in degraded mode" : ""
    return {
      tone: "warning",
      text: `${findings} of ${counts.total} dependencies are not reporting ok${mode}.`,
      caveat: staleness.stale ? `Snapshot is ${staleness.asSpan}` : null,
      caveatDetail:
        "Degraded mode is reported by the platform separately from the dependency checks, so it can be set while every check still reads ok. Both are shown as the platform stated them.",
    }
  }

  return {
    tone: "ok",
    text: `All ${counts.total} reported dependencies are ok and degraded mode is off.`,
    caveat: staleness.stale ? `Snapshot is ${staleness.asSpan}` : "Observation, not certification",
    caveatDetail: staleness.stale
      ? `The page marks a snapshot stale after ${PLATFORM_STALE_AFTER_SECONDS / 60} minutes. These values describe the last observation, not the present.`
      : "One successful read of one snapshot. Availability over a window, incident history and evidence coverage are separate contracts and are not connected to this page.",
  }
}

export type PlatformTile = {
  label: string
  value: string
  helper: string | null
  tone: "default" | "warning" | "critical" | "success"
}

/** Only quantities and durations are tiled; words like "Degraded" are read in the status line. */
export function platformTiles(input: {
  health: PublicPlatformHealth | null
  staleness: LiveStaleness
}): PlatformTile[] {
  const health = input.health
  const counts = platformDependencyCounts(platformDependencyEntries(health))

  return [
    {
      label: "Snapshot age",
      value: health ? input.staleness.label : "Not reported",
      helper: health
        ? `Stale after ${PLATFORM_STALE_AFTER_SECONDS / 60} min · observed ${formatGovernStamp(health.observed_at)}`
        : "No observation time was returned.",
      tone: input.staleness.stale ? "warning" : "default",
    },
    {
      label: "Dependencies reporting ok",
      value: health ? `${formatGovernNumber(counts.ok)} of ${formatGovernNumber(counts.total)}` : "Not reported",
      helper: health
        ? `${formatGovernNumber(counts.degraded)} degraded · ${formatGovernNumber(counts.unavailable)} unavailable`
        : null,
      tone: counts.unavailable > 0 ? "critical" : counts.degraded > 0 ? "warning" : health ? "success" : "default",
    },
    {
      label: "Ingestion lag",
      value: health?.ingestion_lag_seconds == null ? "Not reported" : formatSeconds(health.ingestion_lag_seconds),
      helper:
        health?.ingestion_lag_seconds == null
          ? "The snapshot carries no lag measurement."
          : "A single reading, not a trend.",
      tone: "default",
    },
    {
      label: "Dead-letter depth",
      value: health?.dlq_depth == null ? "Not reported" : formatGovernNumber(health.dlq_depth),
      helper:
        health?.dlq_depth == null
          ? "The snapshot carries no queue depth."
          : health.dlq_depth > 0
            ? "Items reported as waiting for handling."
            : "Reported empty at the time of this read.",
      tone: health?.dlq_depth != null && health.dlq_depth > 0 ? "warning" : "default",
    },
  ]
}

export type PlatformField = {
  label: string
  value: string
  /** Where the value came from, or why it is missing. */
  detail: string
  tone: "default" | "warning" | "muted"
}

export function platformPipelineFields(health: PublicPlatformHealth | null): PlatformField[] {
  return [
    {
      label: "Ingestion lag",
      value: health?.ingestion_lag_seconds == null ? "Not reported" : formatSeconds(health.ingestion_lag_seconds),
      detail:
        health?.ingestion_lag_seconds == null
          ? "ingestion_lag_seconds was null in this snapshot. Nothing is carried over from an earlier read."
          : "ingestion_lag_seconds as the platform reported it, for this one observation.",
      tone: health?.ingestion_lag_seconds == null ? "muted" : "default",
    },
    {
      label: "Dead-letter queue depth",
      value: health?.dlq_depth == null ? "Not reported" : formatGovernNumber(health.dlq_depth),
      detail:
        health?.dlq_depth == null
          ? "dlq_depth was null in this snapshot."
          : "dlq_depth counts items the platform parked. Their contents and failure reasons are not part of this contract.",
      tone: health?.dlq_depth != null && health.dlq_depth > 0 ? "warning" : health?.dlq_depth == null ? "muted" : "default",
    },
    {
      label: "Outbox watermark",
      value:
        health?.outbox_max_aggregate_seq == null
          ? "Not reported"
          : formatGovernNumber(health.outbox_max_aggregate_seq),
      detail:
        health?.outbox_max_aggregate_seq == null
          ? "outbox_max_aggregate_seq was null in this snapshot."
          : "The highest aggregate sequence the outbox had reached at observation time. It is a position, not a throughput.",
      tone: health?.outbox_max_aggregate_seq == null ? "muted" : "default",
    },
    {
      label: "Serving mode",
      value: health ? (health.degraded_mode ? "Degraded" : "Normal") : "Not reported",
      detail: health
        ? "degraded_mode is set by the platform and is independent of the dependency checks, so it can be true while every check reads ok."
        : "No snapshot, so no mode.",
      tone: health?.degraded_mode ? "warning" : "default",
    },
  ]
}

/**
 * `last_restore_drill` is a free-form object on the contract; it has no recorded shape.
 * Only fields that read as the expected type are used, and the keys that came back are listed
 * so an operator can see what the platform actually sent.
 */
export type RestoreDrillReading = {
  recorded: boolean
  status: string | null
  completedAt: string | null
  durationSeconds: number | null
  keys: string[]
}

export function readRestoreDrill(drill: Record<string, unknown> | null | undefined): RestoreDrillReading {
  if (!drill) return { recorded: false, status: null, completedAt: null, durationSeconds: null, keys: [] }
  const status = drill.status
  const completedAt = drill.completed_at
  const duration = drill.duration_seconds
  return {
    recorded: true,
    status: typeof status === "string" && status.trim() ? status.trim() : null,
    completedAt:
      typeof completedAt === "string" && !Number.isNaN(Date.parse(completedAt)) ? completedAt : null,
    durationSeconds: typeof duration === "number" && Number.isFinite(duration) ? duration : null,
    keys: Object.keys(drill),
  }
}

export function platformRecoveryFields(
  health: PublicPlatformHealth | null,
  nowMs: number | null,
): PlatformField[] {
  const drill = readRestoreDrill(health?.last_restore_drill)
  const status = drill.status
  const statusTone: PlatformField["tone"] =
    status?.toLowerCase() === "passed" ? "default" : status?.toLowerCase() === "failed" ? "warning" : "muted"

  return [
    {
      label: "Last backup",
      value: health?.last_backup_at ? formatGovernStamp(health.last_backup_at) : "Not recorded",
      detail: health?.last_backup_at
        ? `Reported by the snapshot · ${formatLiveRelative(health.last_backup_at, nowMs)}`
        : "last_backup_at was null. No earlier snapshot is reused to fill it in.",
      tone: health?.last_backup_at ? "default" : "muted",
    },
    {
      label: "Restore drill status",
      value: status ?? (drill.recorded ? "Recorded, status unreadable" : "Not recorded"),
      detail: status
        ? `The drill record came back with status "${status}". The console has no recorded vocabulary for this field, so it is printed as received.`
        : drill.recorded
          ? `A drill record exists with keys ${drill.keys.join(", ") || "none"}; none of them is a readable status.`
          : "last_restore_drill was null. A backup that has never been restored is not proven restorable.",
      tone: status ? statusTone : "muted",
    },
    {
      label: "Restore drill completed",
      value: drill.completedAt ? formatGovernStamp(drill.completedAt) : "Not recorded",
      detail: drill.completedAt
        ? `Reported by the snapshot · ${formatLiveRelative(drill.completedAt, nowMs)}`
        : "The drill record carried no parseable completed_at.",
      tone: drill.completedAt ? "default" : "muted",
    },
    {
      label: "Restore drill duration",
      value: drill.durationSeconds == null ? "Not recorded" : formatSeconds(drill.durationSeconds),
      detail:
        drill.durationSeconds == null
          ? "The drill record carried no numeric duration_seconds."
          : "duration_seconds as reported for that drill.",
      tone: drill.durationSeconds == null ? "muted" : "default",
    },
    {
      label: "Retention horizon",
      value: health ? `${formatGovernNumber(health.retention_horizon_days)} days` : "Not reported",
      detail: health
        ? "retention_horizon_days is a configured value the platform echoes. Nothing here verifies that retention was enforced."
        : "No snapshot, so no horizon.",
      tone: "default",
    },
  ]
}

export type PlatformDigest = {
  reported: boolean
  value: string | null
  detail: string
}

export function platformDigest(health: PublicPlatformHealth | null): PlatformDigest {
  const value = health?.deploy_image_digest ?? null
  return {
    reported: Boolean(value),
    value,
    detail: value
      ? "deploy_image_digest as the platform reported it. The console cannot resolve a digest to a build, a release, or a set of changes."
      : "deploy_image_digest was null, so this snapshot does not say which build is deployed.",
  }
}

export const PLATFORM_PENDING: { title: string; contract: string; description: string }[] = [
  {
    title: "Check latency history",
    contract: "operator.platform.history.v1",
    description: "The snapshot carries the result of one check, not how long it took or how it trended.",
  },
  {
    title: "Availability over a window",
    contract: "operator.platform.history.v1",
    description: "A single ok cannot be read as uptime. No window, and no percentage, is drawn from one observation.",
  },
  {
    title: "Incident feed",
    contract: "operator.incidents.list.v1",
    description: "Whether a reported dependency problem became an incident is decided outside this contract.",
  },
  {
    title: "Service objectives",
    contract: "operator.slo.history.v1",
    description: "Nothing on this page is comparable to an objective, because no objective is connected.",
  },
]

export const PLATFORM_NOTES: { lead: string; body: string }[] = [
  {
    lead: "One contract, one read.",
    body: "Every value on this page comes from a single operator.platform.health.v1 snapshot taken when the page was read. There is no second source to compare it with and no history to blend into it.",
  },
  {
    lead: "A dependency status is the platform's own check result.",
    body: "It is not a certification, a probe run by the console, or a measurement of user impact. The console re-reads it; it does not verify it.",
  },
  {
    lead: "Null means not recorded, never zero.",
    body: "A null backup time, drill, digest or watermark is shown as not recorded. Absence is reported as absence and is never filled from the previous snapshot.",
  },
  {
    lead: "Staleness is measured from the reported observation time.",
    body: `A snapshot older than ${PLATFORM_STALE_AFTER_SECONDS / 60} minutes is marked stale, and both live surfaces use that same bound so "stale" cannot mean two different ages.`,
  },
  {
    lead: "The restore drill has no fixed shape.",
    body: "last_restore_drill is an object the contract does not constrain. Only fields that arrive as the expected type are read; the rest are listed by key so nothing is silently dropped.",
  },
]
