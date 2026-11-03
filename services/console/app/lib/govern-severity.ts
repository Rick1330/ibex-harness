import type { PlatformDependencyStatus } from "@/lib/platform-readiness"

/**
 * The severity words the console is allowed to use.
 *
 * Drift signals, platform issues, incident rows and overview attention items all report with these
 * three values, so an operator reads the same escalation word on every surface. Codes that arrive
 * from upstream (`SEV-2`, `P1`, `high`) are never displayed as severity: they are either mapped onto
 * one of these three by the contract that owns them, or shown verbatim as a raw field value.
 */
export type GovernSeverity = "critical" | "warning" | "info"

export const GOVERN_SEVERITIES = ["critical", "warning", "info"] as const
export type GovernSeverityFilter = GovernSeverity | "all"

export const GOVERN_SEVERITY_LABELS: Record<GovernSeverity, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
}

export const GOVERN_SEVERITY_MEANING: Record<GovernSeverity, string> = {
  critical: "Something is broken or a guarantee is already violated. It needs an owner now.",
  warning: "A guarantee is at risk or only partly held. It needs reading before it becomes critical.",
  info: "Worth knowing, with nothing currently at stake. No action is implied.",
}

/** Lower number sorts first, so critical rows lead any list built from this order. */
export const GOVERN_SEVERITY_ORDER: Record<GovernSeverity, number> = { critical: 0, warning: 1, info: 2 }

export function compareGovernSeverity(left: GovernSeverity, right: GovernSeverity): number {
  return GOVERN_SEVERITY_ORDER[left] - GOVERN_SEVERITY_ORDER[right]
}

/**
 * A dependency that is not reachable is critical; one that is merely degraded is a warning.
 * `ok` has no severity because it produces no attention row.
 */
export function severityForDependency(status: PlatformDependencyStatus): GovernSeverity | null {
  if (status === "unavailable") return "critical"
  if (status === "degraded") return "warning"
  return null
}

export function isGovernSeverity(value: string): value is GovernSeverity {
  return (GOVERN_SEVERITIES as readonly string[]).includes(value)
}
