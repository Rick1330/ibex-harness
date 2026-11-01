/**
 * Recorded preview fixtures for the Budgets surface.
 *
 * `operator.budgets.reservations.v1` is defined as the intended contract but is not served by the
 * BFF, and no certified accounting watermark exists in this repository. Every amount below is a
 * fixture, and no figure here may be presented as final cost.
 */

export const BUDGET_RESERVATIONS_CONTRACT = "operator.budgets.reservations.v1"

export const BUDGET_WATERMARK_PENDING =
  "Spend is not joined to a certified accounting watermark, so remaining and projected figures stay illustrative."

/* ------------------------------------------------------------------ scopes */

export type BudgetScopeKind = "workspace" | "agent" | "environment" | "api_key"

export const BUDGET_SCOPE_LABELS: Record<BudgetScopeKind, string> = {
  workspace: "Workspace",
  agent: "Agent",
  environment: "Environment",
  api_key: "API key",
}

export const BUDGET_SCOPE_KINDS = Object.keys(BUDGET_SCOPE_LABELS) as BudgetScopeKind[]

export type Enforcement = "hard" | "soft" | "warn_only"

export const ENFORCEMENT_LABELS: Record<Enforcement, string> = {
  hard: "Hard ceiling",
  soft: "Soft ceiling",
  warn_only: "Warn only",
}

export const ENFORCEMENT_MEANING: Record<Enforcement, string> = {
  hard: "The runtime refuses a run once the reservation would exceed the limit.",
  soft: "The runtime keeps admitting work but raises a drift-visible overage.",
  warn_only: "Nothing is refused; the limit exists to be reported on.",
}

export const ENFORCEMENTS = Object.keys(ENFORCEMENT_LABELS) as Enforcement[]

export type BudgetState = "ok" | "tight" | "exhausted"

export const BUDGET_STATE_LABELS: Record<BudgetState, string> = {
  ok: "Headroom",
  tight: "Close to limit",
  exhausted: "At limit",
}

export type Reservation = {
  id: string
  scopeKind: BudgetScopeKind
  scopeId: string
  label: string
  limitUsd: number
  /** Settled spend. */
  committedUsd: number
  /** In-flight holds that have not settled yet. */
  reservedUsd: number
  enforcement: Enforcement
  windowStart: string
  windowEnd: string
  lastReservationAt: string | null
  /** When the last settled figure was reconciled. Null means never reconciled. */
  watermarkAt: string | null
  note?: string
}

export const BUDGET_WINDOW_LABELS = {
  current: "Current billing window",
  previous: "Previous billing window",
} as const

export type BudgetWindow = keyof typeof BUDGET_WINDOW_LABELS

export const BUDGET_WINDOWS: BudgetWindow[] = ["current", "previous"]

export const BUDGET_RESERVATIONS: Reservation[] = [
  {
    id: "bud_workspace",
    scopeKind: "workspace",
    scopeId: "ws_42",
    label: "Workspace monthly budget",
    limitUsd: 4200,
    committedUsd: 3011.4,
    reservedUsd: 182.6,
    enforcement: "hard",
    windowStart: "2026-10-01T00:00:00Z",
    windowEnd: "2026-11-01T00:00:00Z",
    lastReservationAt: "2026-10-30T14:58:12Z",
    watermarkAt: "2026-10-30T09:00:00Z",
  },
  {
    id: "bud_support_agent",
    scopeKind: "agent",
    scopeId: "ag_support_triage",
    label: "Support triage agent",
    limitUsd: 1400,
    committedUsd: 1268.9,
    reservedUsd: 96.2,
    enforcement: "hard",
    windowStart: "2026-10-01T00:00:00Z",
    windowEnd: "2026-11-01T00:00:00Z",
    lastReservationAt: "2026-10-30T15:07:41Z",
    watermarkAt: "2026-10-30T09:00:00Z",
    note: "Consumed by the v14 model change on 20 Oct; see the drift signal on tool-call rate.",
  },
  {
    id: "bud_billing_agent",
    scopeKind: "agent",
    scopeId: "ag_billing_analyst",
    label: "Billing assistant",
    limitUsd: 600,
    committedUsd: 214.75,
    reservedUsd: 12.4,
    enforcement: "soft",
    windowStart: "2026-10-01T00:00:00Z",
    windowEnd: "2026-11-01T00:00:00Z",
    lastReservationAt: "2026-10-30T11:20:03Z",
    watermarkAt: "2026-10-30T09:00:00Z",
  },
  {
    id: "bud_env_prod",
    scopeKind: "environment",
    scopeId: "env_production",
    label: "Production environment",
    limitUsd: 3000,
    committedUsd: 2974.1,
    reservedUsd: 40.0,
    enforcement: "hard",
    windowStart: "2026-10-01T00:00:00Z",
    windowEnd: "2026-11-01T00:00:00Z",
    lastReservationAt: "2026-10-30T15:11:26Z",
    watermarkAt: "2026-10-30T09:00:00Z",
    note: "A hard ceiling at 99% means the next reservation may be refused. This is the row that matters at 03:00.",
  },
  {
    id: "bud_key_ops",
    scopeKind: "api_key",
    scopeId: "key_ops_91",
    label: "Operations key key_ops_91",
    limitUsd: 250,
    committedUsd: 88.2,
    reservedUsd: 0,
    enforcement: "warn_only",
    windowStart: "2026-10-01T00:00:00Z",
    windowEnd: "2026-11-01T00:00:00Z",
    lastReservationAt: "2026-10-27T16:42:10Z",
    watermarkAt: null,
    note: "Never reconciled against the accounting watermark, so the committed figure is a running total only.",
  },
]

export function reservationsFor(window: BudgetWindow): Reservation[] {
  if (window === "current") return BUDGET_RESERVATIONS
  // The previous window is reported as a closed set: nothing is in flight.
  return BUDGET_RESERVATIONS.map((row) => ({
    ...row,
    committedUsd: Math.round(row.committedUsd * 0.82 * 100) / 100,
    reservedUsd: 0,
    windowStart: "2026-09-01T00:00:00Z",
    windowEnd: "2026-10-01T00:00:00Z",
    lastReservationAt: "2026-09-30T22:14:03Z",
  }))
}

export function budgetCommittedPercent(row: Reservation): number {
  return row.limitUsd === 0 ? 0 : (row.committedUsd / row.limitUsd) * 100
}

export function budgetReservedPercent(row: Reservation): number {
  return row.limitUsd === 0 ? 0 : (row.reservedUsd / row.limitUsd) * 100
}

export function budgetHeadroomUsd(row: Reservation): number {
  return Math.max(0, row.limitUsd - row.committedUsd - row.reservedUsd)
}

export function budgetHeadroomPercent(row: Reservation): number {
  return row.limitUsd === 0 ? 0 : (budgetHeadroomUsd(row) / row.limitUsd) * 100
}

export function budgetState(row: Reservation): BudgetState {
  const used = (row.committedUsd + row.reservedUsd) / row.limitUsd
  if (used >= 1) return "exhausted"
  if (used >= 0.9) return "tight"
  return "ok"
}

export function budgetUsd(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function budgetTotals(rows: Reservation[] = BUDGET_RESERVATIONS) {
  const limit = rows.reduce((sum, row) => sum + row.limitUsd, 0)
  const committed = rows.reduce((sum, row) => sum + row.committedUsd, 0)
  const reserved = rows.reduce((sum, row) => sum + row.reservedUsd, 0)
  return {
    limit,
    committed,
    reserved,
    headroom: Math.max(0, limit - committed - reserved),
    rows,
    tight: rows.filter((row) => budgetState(row) === "tight").length,
    exhausted: rows.filter((row) => budgetState(row) === "exhausted").length,
    unreconciled: rows.filter((row) => row.watermarkAt === null).length,
  }
}

/* --------------------------------------------------------------- lifecycle */

export type ReservationEventType =
  | "created"
  | "reserved"
  | "committed"
  | "released"
  | "expired"
  | "denied"

export const RESERVATION_EVENT_LABELS: Record<ReservationEventType, string> = {
  created: "Reservation opened",
  reserved: "Amount held",
  committed: "Hold settled",
  released: "Hold released",
  expired: "Reservation expired",
  denied: "Run refused",
}

export const RESERVATION_EVENT_MEANING: Record<ReservationEventType, string> = {
  created: "A window was opened for the scope.",
  reserved: "An in-flight hold was placed against the limit.",
  committed: "The hold settled into real, reported spend.",
  released: "The hold was returned to headroom without settling.",
  expired: "A hold aged out without settling.",
  denied: "The runtime refused work because the hold would have exceeded the limit.",
}

export type ReservationEvent = {
  id: string
  at: string
  type: ReservationEventType
  reservationId: string
  scopeLabel: string
  amountUsd: number | null
  actor: string
  actorType: "person" | "service" | "system"
  detail: string
  /** Link to the audit event that recorded the same mutation, when one exists in fixtures. */
  auditEventId?: string
}

export const BUDGET_LIFECYCLE: ReservationEvent[] = [
  {
    id: "bres_01",
    at: "2026-10-30T15:11:26Z",
    type: "reserved",
    reservationId: "bud_env_prod",
    scopeLabel: "Production environment",
    amountUsd: 40,
    actor: "Budget worker",
    actorType: "service",
    detail: "Held against a run admitted at the ceiling. The hold is what keeps two concurrent runs from overspending together.",
  },
  {
    id: "bres_02",
    at: "2026-10-30T15:07:41Z",
    type: "reserved",
    reservationId: "bud_support_agent",
    scopeLabel: "Support triage agent",
    amountUsd: 96.2,
    actor: "Budget worker",
    actorType: "service",
    detail: "Held for the current batch of support runs.",
  },
  {
    id: "bres_03",
    at: "2026-10-30T14:58:12Z",
    type: "committed",
    reservationId: "bud_workspace",
    scopeLabel: "Workspace monthly budget",
    amountUsd: 128.4,
    actor: "Budget worker",
    actorType: "service",
    detail: "Settled from a hold opened at 13:40. Committed spend is the only figure that should be read as cost.",
  },
  {
    id: "bres_04",
    at: "2026-10-30T13:58:21Z",
    type: "expired",
    reservationId: "bud_env_prod",
    scopeLabel: "Production environment",
    amountUsd: 62.1,
    actor: "Budget worker",
    actorType: "system",
    detail: "The run never reported back, so the hold aged out and returned to headroom.",
    auditEventId: "evt_90bd14",
  },
  {
    id: "bres_05",
    at: "2026-10-30T06:31:19Z",
    type: "denied",
    reservationId: "bud_env_prod",
    scopeLabel: "Production environment",
    amountUsd: 1082,
    actor: "Policy engine",
    actorType: "service",
    detail: "Run run_55ac02 asked for more than the remaining ceiling and was refused before any provider call.",
    auditEventId: "evt_17d5b0",
  },
  {
    id: "bres_06",
    at: "2026-10-30T03:12:44Z",
    type: "released",
    reservationId: "bud_billing_agent",
    scopeLabel: "Billing assistant",
    amountUsd: 18.9,
    actor: "Budget worker",
    actorType: "service",
    detail: "The run finished below its estimate, so the unused hold returned to headroom.",
  },
  {
    id: "bres_07",
    at: "2026-10-01T00:00:04Z",
    type: "created",
    reservationId: "bud_workspace",
    scopeLabel: "Workspace monthly budget",
    amountUsd: 4200,
    actor: "Mira Chen",
    actorType: "person",
    detail: "Window opened for October with a hard ceiling.",
  },
]

export function lifecycleFor(reservationId: string): ReservationEvent[] {
  return BUDGET_LIFECYCLE.filter((event) => event.reservationId === reservationId)
}

export function lifecycleCounts(rows: ReservationEvent[] = BUDGET_LIFECYCLE) {
  return {
    denied: rows.filter((event) => event.type === "denied").length,
    expired: rows.filter((event) => event.type === "expired").length,
    open: rows.filter((event) => event.type === "reserved").length,
  }
}

/* ------------------------------------------------------------------ status */

export function budgetStatusLine(): { tone: "muted"; text: string; detail: string } {
  const totals = budgetTotals()
  return {
    tone: "muted",
    text: "Sample reservations. Spend is not joined to a certified accounting watermark, so no figure here is final cost.",
    detail: [
      `${totals.rows.length} scopes in this window: ${budgetUsd(totals.committed)} committed, ${budgetUsd(totals.reserved)} held.`,
      `${totals.tight} close to their limit, ${totals.exhausted} at their limit.`,
      totals.unreconciled > 0 ? `${totals.unreconciled} scope(s) have never been reconciled against a watermark.` : "Every scope is reconciled to the last watermark.",
    ].join(" "),
  }
}

export function budgetInFlightText(row: Reservation): string {
  if (row.reservedUsd === 0) return "No holds in flight"
  return `${budgetUsd(row.reservedUsd)} held`
}

/* ---------------------------------------------------------------- filtering */

export type BudgetFilter = {
  q: string
  scope: BudgetScopeKind | "all"
  enforcement: Enforcement | "all"
}

export function filterReservations(rows: Reservation[], state: BudgetFilter): Reservation[] {
  const needle = state.q.toLowerCase()
  return rows.filter(
    (row) =>
      (state.scope === "all" || row.scopeKind === state.scope) &&
      (state.enforcement === "all" || row.enforcement === state.enforcement) &&
      (needle === "" || `${row.label} ${row.scopeId} ${row.id}`.toLowerCase().includes(needle)),
  )
}

export function filterLifecycle(rows: ReservationEvent[], state: BudgetFilter): ReservationEvent[] {
  const needle = state.q.toLowerCase()
  return rows.filter(
    (event) =>
      (state.scope === "all" || reservationScopeKind(event.reservationId) === state.scope) &&
      (needle === "" ||
        `${event.scopeLabel} ${event.detail} ${RESERVATION_EVENT_LABELS[event.type]} ${event.actor}`.toLowerCase().includes(needle)),
  )
}

export function reservationScopeKind(reservationId: string): BudgetScopeKind | null {
  return BUDGET_RESERVATIONS.find((row) => row.id === reservationId)?.scopeKind ?? null
}

export function reservationById(reservationId: string): Reservation | null {
  return BUDGET_RESERVATIONS.find((row) => row.id === reservationId) ?? null
}
