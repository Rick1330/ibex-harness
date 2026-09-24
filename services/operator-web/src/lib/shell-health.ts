/**
 * Global freshness / connection health (sidebar → top bar).
 * Fixture-backed stand-in for SSE drain + ClickHouse lag measurement.
 */

export type FreshnessState =
  "live" | "historical" | "reconnecting" | "degraded" | "partial" | "stale"

export type ConnectionState =
  "ready" | "draining" | "reconnecting" | "unreachable"

export type ShellHealth = {
  freshness: FreshnessState
  connection: ConnectionState
  /** Last successful page/query sync (ISO). */
  last_successful_sync: string
  /** ClickHouse / SSE lag in ms when measurable. */
  lag_ms: number | null
  detail: string
}

/** Default live fixture — fixed sync time so SSR/client hydration matches. */
export const SHELL_HEALTH: ShellHealth = {
  freshness: "live",
  connection: "ready",
  last_successful_sync: "2026-02-11T14:22:00.000Z",
  lag_ms: 180,
  detail: "/ready ok · SSE drain healthy · CH lag 180ms",
}

export const FRESHNESS_TONE: Record<
  FreshnessState,
  { dot: string; label: string }
> = {
  live: { dot: "bg-emerald-500", label: "live" },
  historical: { dot: "bg-sky-500", label: "historical" },
  reconnecting: { dot: "bg-amber-500", label: "reconnecting" },
  degraded: { dot: "bg-amber-600", label: "degraded" },
  partial: { dot: "bg-orange-500", label: "partial" },
  stale: { dot: "bg-destructive", label: "stale" },
}
