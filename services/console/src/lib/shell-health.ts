/**
 * Preview-only freshness/connection design tokens (sidebar → top bar).
 * They are not health telemetry; live health comes from the D1 API contract.
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

/** Preview-only fixture — never implies a live API, SSE, or ClickHouse connection. */
export const SHELL_HEALTH: ShellHealth = {
  freshness: "historical",
  connection: "unreachable",
  last_successful_sync: "2026-02-11T14:22:00.000Z",
  lag_ms: null,
  detail: "Preview fixture only — no live /ready, SSE, or ClickHouse connection.",
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
