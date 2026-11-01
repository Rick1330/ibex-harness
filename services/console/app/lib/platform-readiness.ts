import type { PublicPlatformHealth } from "~~/shared/operator/public"

export type PlatformDependencyStatus = "ok" | "degraded" | "unavailable"
export type PlatformDependencyEntry = [string, PlatformDependencyStatus]
export type PlatformReadinessState =
  | "ready"
  | "degraded"
  | "blocked"
  | "no-checks"
  | "unavailable"
  | "auth"
  | "loading"

/**
 * A platform snapshot stops being a statement about the present after this many seconds.
 * Both live surfaces use one bound so that "stale" cannot mean two different ages.
 */
export const PLATFORM_STALE_AFTER_SECONDS = 5 * 60

export type PlatformDependencyCounts = {
  total: number
  ok: number
  degraded: number
  unavailable: number
}

const DEPENDENCY_SEVERITY: Record<PlatformDependencyStatus, number> = {
  unavailable: 0,
  degraded: 1,
  ok: 2,
}

const DEPENDENCY_LABELS: Record<string, string> = {
  auth_grpc: "Auth gRPC",
  clickhouse: "ClickHouse",
  context_grpc: "Context gRPC",
}

export function platformDependencyEntries(
  health: PublicPlatformHealth | null,
): PlatformDependencyEntry[] {
  return Object.entries(health?.dependency_health ?? {}) as PlatformDependencyEntry[]
}

export function platformDependencyCounts(
  entries: PlatformDependencyEntry[],
): PlatformDependencyCounts {
  return entries.reduce<PlatformDependencyCounts>(
    (counts, [, status]) => {
      counts.total += 1
      counts[status] += 1
      return counts
    },
    { total: 0, ok: 0, degraded: 0, unavailable: 0 },
  )
}

export function sortPlatformDependencies(
  entries: PlatformDependencyEntry[],
): PlatformDependencyEntry[] {
  return [...entries].sort(([leftName, leftStatus], [rightName, rightStatus]) => {
    const severity = DEPENDENCY_SEVERITY[leftStatus] - DEPENDENCY_SEVERITY[rightStatus]
    return severity || leftName.localeCompare(rightName)
  })
}

export function platformReadinessState(input: {
  health: PublicPlatformHealth | null
  authIssue: boolean
  loading: boolean
}): PlatformReadinessState {
  if (input.health) {
    const entries = platformDependencyEntries(input.health)
    if (!entries.length) return "no-checks"
    if (entries.some(([, status]) => status === "unavailable")) return "blocked"
    if (input.health.degraded_mode || entries.some(([, status]) => status === "degraded")) {
      return "degraded"
    }
    return "ready"
  }
  if (input.authIssue) return "auth"
  if (input.loading) return "loading"
  return "unavailable"
}

export function platformDependencyName(name: string): string {
  const label = DEPENDENCY_LABELS[name]
  if (label) return label
  const words = name.replaceAll("_", " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function platformDependencyStatusLabel(status: PlatformDependencyStatus): string {
  if (status === "ok") return "Ok"
  if (status === "degraded") return "Degraded"
  return "Unavailable"
}
