import { GOVERN_NOW } from "@/lib/govern-format"

/**
 * Recorded preview fixtures for the Evidence surface.
 *
 * `operator.evidence.summary.v1` is not implemented anywhere in this repository, so every
 * number below is a fixture. Nothing here may be presented as a certified completeness claim.
 */

export const EVIDENCE_SUMMARY_CONTRACT = "operator.evidence.summary.v1 [NEEDS-BACKEND]"

export const EVIDENCE_PENDING_SUMMARY =
  "No evidence summary is connected. Coverage is shown from recorded preview fixtures, so no completeness claim is made."

/* ------------------------------------------------------------------ tiers */

export type EvidenceTier = "evidence" | "metadata" | "redacted" | "uncertified" | "unavailable"

export const EVIDENCE_TIER_LABELS: Record<EvidenceTier, string> = {
  evidence: "Evidence",
  metadata: "Metadata",
  redacted: "Redacted",
  uncertified: "Uncertified",
  unavailable: "Unavailable",
}

export const EVIDENCE_TIER_MEANING: Record<EvidenceTier, string> = {
  evidence: "A certified evidence record exists and can be re-read by digest.",
  metadata: "The evidence record is certified; the payload itself is not retained here.",
  redacted: "Fields were removed before storage. Metadata remains readable; the removed content does not.",
  uncertified: "Observed in a read response with no evidence record behind it.",
  unavailable: "Publication did not produce a usable record. Never estimated.",
}

export const EVIDENCE_TIERS = Object.keys(EVIDENCE_TIER_LABELS) as EvidenceTier[]

export function evidenceTierLabel(tier: EvidenceTier): string {
  return EVIDENCE_TIER_LABELS[tier]
}

/* --------------------------------------------------------------- producers */

export type EvidenceComponentId =
  | "memory.extraction"
  | "context.assembly"
  | "proxy.relay"
  | "policy.evaluate"
  | "gdpr.deletion"
  | "billing.ledger"

export type CaptureMode = "dual_write_outbox" | "inline" | "batch_projection"

export const CAPTURE_MODE_LABELS: Record<CaptureMode, string> = {
  dual_write_outbox: "Dual-write outbox",
  inline: "Inline write",
  batch_projection: "Batch projection",
}

export type EvidenceProducerRow = {
  id: EvidenceComponentId
  label: string
  service: string
  captureMode: CaptureMode
  /** Records touched in the window, keyed by tier. */
  counts: Record<EvidenceTier, number>
  lastEvidenceAt: string | null
  /** Oldest record in the window still waiting on its evidence row. */
  oldestPendingAt: string | null
  note: string
}

export const EVIDENCE_PRODUCERS: EvidenceProducerRow[] = [
  {
    id: "memory.extraction",
    label: "Memory extraction",
    service: "workers.memory",
    captureMode: "dual_write_outbox",
    counts: { evidence: 1184, metadata: 268, redacted: 64, uncertified: 41, unavailable: 3 },
    lastEvidenceAt: "2026-10-30T15:04:12Z",
    oldestPendingAt: "2026-10-30T11:42:03Z",
    note: "Writes the evidence row in the same transaction as the memory, then publishes to the outbox.",
  },
  {
    id: "context.assembly",
    label: "Context assembly",
    service: "context.engine",
    captureMode: "inline",
    counts: { evidence: 0, metadata: 3902, redacted: 0, uncertified: 0, unavailable: 0 },
    lastEvidenceAt: null,
    oldestPendingAt: null,
    note: "Assembly results are recorded as metadata only: the packed context is not retained, so no digest can be re-read.",
  },
  {
    id: "proxy.relay",
    label: "LLM proxy relay",
    service: "proxy.relay",
    captureMode: "dual_write_outbox",
    counts: { evidence: 6420, metadata: 411, redacted: 318, uncertified: 96, unavailable: 27 },
    lastEvidenceAt: "2026-10-30T15:11:02Z",
    oldestPendingAt: "2026-10-30T09:18:44Z",
    note: "Unavailable rows are deliveries that were dead-lettered before an evidence row could be written.",
  },
  {
    id: "policy.evaluate",
    label: "Policy evaluation",
    service: "policy.engine",
    captureMode: "inline",
    counts: { evidence: 2210, metadata: 0, redacted: 0, uncertified: 12, unavailable: 0 },
    lastEvidenceAt: "2026-10-30T15:09:31Z",
    oldestPendingAt: "2026-10-30T13:55:07Z",
    note: "Each decision stores the snapshot digest it was evaluated against.",
  },
  {
    id: "gdpr.deletion",
    label: "Deletion and tombstones",
    service: "workers.retention",
    captureMode: "dual_write_outbox",
    counts: { evidence: 46, metadata: 0, redacted: 5, uncertified: 4, unavailable: 2 },
    lastEvidenceAt: "2026-10-30T12:40:19Z",
    oldestPendingAt: "2026-10-29T22:14:51Z",
    note: "A tombstone is only certified once every downstream delete has reported back; see the chain tab.",
  },
  {
    id: "billing.ledger",
    label: "Billing projections",
    service: "analytics.clickhouse",
    captureMode: "batch_projection",
    counts: { evidence: 0, metadata: 0, redacted: 0, uncertified: 812, unavailable: 0 },
    lastEvidenceAt: null,
    oldestPendingAt: null,
    note: "ClickHouse rows are derived, not authoritative. They cannot prove billing, deletion, or audit completeness.",
  },
]

export function evidenceProducerTotal(row: EvidenceProducerRow): number {
  return EVIDENCE_TIERS.reduce((sum, tier) => sum + row.counts[tier], 0)
}

export function evidenceTierPercent(row: EvidenceProducerRow, tier: EvidenceTier): number {
  const total = evidenceProducerTotal(row)
  return total === 0 ? 0 : (row.counts[tier] / total) * 100
}

export function evidenceCoverage(rows: EvidenceProducerRow[] = EVIDENCE_PRODUCERS) {
  const totals: Record<EvidenceTier, number> = { evidence: 0, metadata: 0, redacted: 0, uncertified: 0, unavailable: 0 }
  for (const row of rows) {
    for (const tier of EVIDENCE_TIERS) totals[tier] += row.counts[tier]
  }
  const records = EVIDENCE_TIERS.reduce((sum, tier) => sum + totals[tier], 0)
  return {
    totals,
    records,
    // "Certified" counts only rows whose evidence record can be re-read by digest.
    certifiedPercent: records === 0 ? 0 : (totals.evidence / records) * 100,
    openGap: totals.uncertified + totals.unavailable,
  }
}

/* --------------------------------------------------------------- redaction */

export type EvidenceRedactionRow = {
  id: string
  label: string
  service: string
  proofVersion: string
  metadata: number
  redacted: number
  withheld: number
  droppedFields: { field: string; reason: string }[]
  note: string
}

export const EVIDENCE_REDACTION_ROWS: EvidenceRedactionRow[] = [
  {
    id: "proxy.session.evidence",
    label: "Session evidence sanitizer",
    service: "proxy.session.evidence",
    proofVersion: "session-metadata-allowlist/v1",
    metadata: 6420,
    redacted: 318,
    withheld: 12,
    droppedFields: [
      { field: "span.attributes", reason: "Span attributes are not on the positive allowlist." },
      { field: "tools", reason: "Tool arguments and results are never copied into metadata evidence." },
      { field: "session_events", reason: "Session event bodies stay out of the evidence row." },
      { field: "error_code", reason: "Upstream free-form error strings are removed; status keeps ok or error." },
      { field: "prompt / completion", reason: "Prompt and completion text is not part of this contract." },
    ],
    note: "A row downgrades to redacted when any listed value fails its structural check. Missing tenant, agent, session, request, or trace identity withholds the row instead.",
  },
  {
    id: "worker.capture",
    label: "Capture redaction worker",
    service: "ibex.privacy.apply_capture_redaction",
    proofVersion: "capture-policy/v1",
    metadata: 3902,
    redacted: 64,
    withheld: 0,
    droppedFields: [
      { field: "raw", reason: "Raw payload is stripped under the redacted capture mode." },
      { field: "content", reason: "Content is replaced by markers before archive or projection." },
      { field: "prompt", reason: "Prompt text is removed before the row is persisted." },
    ],
    note: "The worker runs off the proxy hot path. metadata_only never forwards raw payloads; redacted strips raw, content, and prompt keys before persisting.",
  },
  {
    id: "memory.pii",
    label: "Memory PII pipeline",
    service: "memory.pii.service",
    proofVersion: "presidio-analyzer/anonymizer",
    metadata: 1184,
    redacted: 5,
    withheld: 0,
    droppedFields: [
      { field: "CREDIT_CARD", reason: "Detected above the confidence threshold and replaced with a marker." },
      { field: "EMAIL_ADDRESS", reason: "Detected above the confidence threshold and replaced with a marker." },
      { field: "PHONE_NUMBER", reason: "Detected above the confidence threshold and replaced with a marker." },
    ],
    note: "Low-confidence findings are not silently redacted or allowed. The record is quarantined instead, so the operator sees why it left retrieval.",
  },
]

export function filterEvidenceRedaction(rows: EvidenceRedactionRow[], query: string): EvidenceRedactionRow[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return rows
  return rows.filter((row) =>
    matches(`${row.label} ${row.service} ${row.proofVersion} ${row.note} ${row.droppedFields.map((field) => `${field.field} ${field.reason}`).join(" ")}`, needle),
  )
}

/* --------------------------------------------------------------- tombstones */

export type TombstoneSubjectType = "memory" | "session" | "trace" | "agent_run"

export const TOMBSTONE_SUBJECT_LABELS: Record<TombstoneSubjectType, string> = {
  memory: "Memory",
  session: "Session",
  trace: "Trace",
  agent_run: "Run",
}

export type DeletionBasis = "gdpr_erasure" | "retention_expiry" | "operator_delete" | "workspace_offboarding"

export const DELETION_BASIS_LABELS: Record<DeletionBasis, string> = {
  gdpr_erasure: "GDPR Article 17 erasure",
  retention_expiry: "Retention window expired",
  operator_delete: "Operator deletion",
  workspace_offboarding: "Workspace offboarding",
}

export type DownstreamState = "applied" | "pending" | "failed" | "not_required"

export const DOWNSTREAM_STATE_LABELS: Record<DownstreamState, string> = {
  applied: "Applied",
  pending: "Pending",
  failed: "Failed",
  not_required: "Not required",
}

export const DELETION_BASES = Object.keys(DELETION_BASIS_LABELS) as DeletionBasis[]

export type Tombstone = {
  id: string
  subjectType: TombstoneSubjectType
  subjectId: string
  subjectName: string
  deletedAt: string
  requestedBy: string
  requestedByType: "person" | "service"
  basis: DeletionBasis
  /** Copy of the tombstone row itself: written, and hash-chained into the audit log. */
  tombstoneCertified: boolean
  downstream: { postgres: DownstreamState; search_index: DownstreamState; clickhouse: DownstreamState; archive: DownstreamState }
  /** Archive deletion is contractual, not technical: the object is unreferenced and expires on its own term. */
  archiveNote?: string
}

export const EVIDENCE_TOMBSTONES: Tombstone[] = [
  {
    id: "tms_41c0",
    subjectType: "memory",
    subjectId: "mem_7c21f0",
    subjectName: "Memory mem_7c21f0",
    deletedAt: "2026-10-30T12:40:19Z",
    requestedBy: "Retention worker",
    requestedByType: "service",
    basis: "retention_expiry",
    tombstoneCertified: true,
    downstream: { postgres: "applied", search_index: "applied", clickhouse: "applied", archive: "applied" },
  },
  {
    id: "tms_9be2",
    subjectType: "memory",
    subjectId: "mem_18d7ac",
    subjectName: "Memory mem_18d7ac",
    deletedAt: "2026-10-30T09:22:07Z",
    requestedBy: "Mira Chen",
    requestedByType: "person",
    basis: "operator_delete",
    tombstoneCertified: true,
    downstream: { postgres: "applied", search_index: "pending", clickhouse: "applied", archive: "applied" },
  },
  {
    id: "tms_2f77",
    subjectType: "session",
    subjectId: "ses_5210f3",
    subjectName: "Session ses_5210f3",
    deletedAt: "2026-10-29T22:14:51Z",
    requestedBy: "Priya Nair",
    requestedByType: "person",
    basis: "gdpr_erasure",
    tombstoneCertified: true,
    downstream: { postgres: "applied", search_index: "applied", clickhouse: "failed", archive: "not_required" },
    archiveNote: "Session payloads are never written to the archive bucket.",
  },
  {
    id: "tms_6a19",
    subjectType: "trace",
    subjectId: "trc_c41d07",
    subjectName: "Trace trc_c41d07",
    deletedAt: "2026-10-29T18:03:44Z",
    requestedBy: "Priya Nair",
    requestedByType: "person",
    basis: "gdpr_erasure",
    tombstoneCertified: false,
    downstream: { postgres: "applied", search_index: "not_required", clickhouse: "pending", archive: "pending" },
    archiveNote: "Archive object still referenced; the tombstone stays uncertified until the delete is reported.",
  },
  {
    id: "tms_05de",
    subjectType: "agent_run",
    subjectId: "run_55ac02",
    subjectName: "Run run_55ac02",
    deletedAt: "2026-10-28T14:11:29Z",
    requestedBy: "Workspace offboarding",
    requestedByType: "service",
    basis: "workspace_offboarding",
    tombstoneCertified: true,
    downstream: { postgres: "applied", search_index: "applied", clickhouse: "applied", archive: "applied" },
  },
]

export function tombstoneChainComplete(tombstone: Tombstone): boolean {  return (
    tombstone.tombstoneCertified &&
    Object.values(tombstone.downstream).every((state) => state === "applied" || state === "not_required")
  )
}

export function tombstoneOpenSteps(tombstone: Tombstone): DownstreamState[] {
  return Object.values(tombstone.downstream).filter((state) => state === "pending" || state === "failed")
}

/**
 * Where the subject's own history lives. Only targets the audit object route understands are
 * linked; a trace has no audit object page and its id is a fixture, so it stays unlinked.
 */
export function tombstoneHistoryHref(tombstone: Tombstone): string | null {
  switch (tombstone.subjectType) {
    case "agent_run":
      return `/audit/objects/run/${encodeURIComponent(tombstone.subjectId)}`
    case "trace":
      return null
    default:
      return `/audit/objects/${encodeURIComponent(tombstone.subjectType)}/${encodeURIComponent(tombstone.subjectId)}`
  }
}

/* ------------------------------------------------------------------- chain */

export type ChainState = "delivered" | "pending" | "retrying" | "poison" | "gap"

export const CHAIN_STATE_LABELS: Record<ChainState, string> = {
  delivered: "Delivered",
  pending: "Pending",
  retrying: "Retrying",
  poison: "Poison",
  gap: "Sequence gap",
}

export const CHAIN_STATES = Object.keys(CHAIN_STATE_LABELS) as ChainState[]

export type ChainLink = {
  seq: number
  outboxId: string | null
  producer: string
  consumer: string
  kind: string
  state: ChainState
  enqueuedAt: string
  settledAt: string | null
  attempts: number
  lagMs: number | null
  subjectId: string
  detail: string
}

export const EVIDENCE_CHAIN: ChainLink[] = [
  {
    seq: 91_224,
    outboxId: "obx_91224",
    producer: "proxy.relay",
    consumer: "analytics.clickhouse",
    kind: "relay.delivered",
    state: "delivered",
    enqueuedAt: "2026-10-30T15:11:02Z",
    settledAt: "2026-10-30T15:11:04Z",
    attempts: 1,
    lagMs: 2140,
    subjectId: "evt_1c4b70",
    detail: "Consumed on the first attempt.",
  },
  {
    seq: 91_223,
    outboxId: "obx_91223",
    producer: "workers.memory",
    consumer: "search.index",
    kind: "memory.tombstone",
    state: "delivered",
    enqueuedAt: "2026-10-30T12:40:19Z",
    settledAt: "2026-10-30T12:40:22Z",
    attempts: 1,
    lagMs: 2870,
    subjectId: "tms_41c0",
    detail: "Deletion propagated to the vector index.",
  },
  {
    seq: 91_222,
    outboxId: "obx_91222",
    producer: "workers.memory",
    consumer: "search.index",
    kind: "memory.tombstone",
    state: "retrying",
    enqueuedAt: "2026-10-30T09:22:07Z",
    settledAt: null,
    attempts: 4,
    lagMs: null,
    subjectId: "tms_9be2",
    detail: "Index shard returned 503. Backoff is 90s; the tombstone stays partially applied until it lands.",
  },
  {
    seq: 91_221,
    outboxId: "obx_91221",
    producer: "workers.retention",
    consumer: "analytics.clickhouse",
    kind: "trace.erase",
    state: "poison",
    enqueuedAt: "2026-10-29T22:14:51Z",
    settledAt: "2026-10-29T22:44:12Z",
    attempts: 8,
    lagMs: null,
    subjectId: "tms_2f77",
    detail: "Retries exhausted. The row was dead-lettered, so the ClickHouse delete has not been applied.",
  },
  {
    seq: 91_220,
    outboxId: "obx_91220",
    producer: "policy.engine",
    consumer: "audit.append",
    kind: "policy.evaluate",
    state: "delivered",
    enqueuedAt: "2026-10-29T19:05:33Z",
    settledAt: "2026-10-29T19:05:33Z",
    attempts: 1,
    lagMs: 340,
    subjectId: "evt_e4a28d",
    detail: "Appended with the snapshot digest it was evaluated against.",
  },
  {
    seq: 91_219,
    outboxId: null,
    producer: "analytics.clickhouse",
    consumer: "analytics.clickhouse",
    kind: "billing.reservation.commit",
    state: "gap",
    enqueuedAt: "2026-10-29T18:03:44Z",
    settledAt: null,
    attempts: 0,
    lagMs: null,
    subjectId: "seq_91219",
    detail: "No outbox row exists for this sequence number. The gap is detected from the local sequence, not from a verification service.",
  },
  {
    seq: 91_218,
    outboxId: "obx_91218",
    producer: "workers.retention",
    consumer: "archive.object-store",
    kind: "trace.erase",
    state: "pending",
    enqueuedAt: "2026-10-29T18:03:44Z",
    settledAt: null,
    attempts: 1,
    lagMs: null,
    subjectId: "tms_6a19",
    detail: "Awaiting the object-store delete callback.",
  },
]

export function chainStateCounts(links: ChainLink[] = EVIDENCE_CHAIN): Record<ChainState, number> {
  const counts: Record<ChainState, number> = { delivered: 0, pending: 0, retrying: 0, poison: 0, gap: 0 }
  for (const link of links) counts[link.state] += 1
  return counts
}

export function chainNeedsAttention(links: ChainLink[] = EVIDENCE_CHAIN): ChainLink[] {
  return links.filter((link) => link.state !== "delivered")
}

export function chainLagText(link: ChainLink): string {
  if (link.lagMs !== null) return link.lagMs < 1000 ? `${link.lagMs} ms` : `${(link.lagMs / 1000).toFixed(1)} s`
  if (link.settledAt) return "Not recorded"
  return "Still open"
}

/* ------------------------------------------------------------------ ranges */

export type EvidenceRange = "24h" | "7d" | "30d"

export const EVIDENCE_RANGES: EvidenceRange[] = ["24h", "7d", "30d"]

export const EVIDENCE_RANGE_LABELS: Record<EvidenceRange, string> = {
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
}

export function evidenceRangeCutoff(range: EvidenceRange): number {
  const hours = range === "24h" ? 24 : range === "7d" ? 24 * 7 : 24 * 30
  return GOVERN_NOW - hours * 3_600_000
}

export function evidenceTombstonesInRange(range: EvidenceRange): Tombstone[] {
  const cutoff = evidenceRangeCutoff(range)
  return EVIDENCE_TOMBSTONES.filter((tombstone) => Date.parse(tombstone.deletedAt) >= cutoff)
}

export function evidenceChainInRange(range: EvidenceRange): ChainLink[] {
  const cutoff = evidenceRangeCutoff(range)
  return EVIDENCE_CHAIN.filter((link) => Date.parse(link.enqueuedAt) >= cutoff)
}

/** Fixture multipliers keep the ledger honest about what each window actually covers. */
const EVIDENCE_WINDOW_FACTOR: Record<EvidenceRange, number> = { "24h": 1, "7d": 6.4, "30d": 26.8 }

export function evidenceProducersFor(range: EvidenceRange): EvidenceProducerRow[] {
  const factor = EVIDENCE_WINDOW_FACTOR[range]
  if (factor === 1) return EVIDENCE_PRODUCERS
  return EVIDENCE_PRODUCERS.map((row) => ({
    ...row,
    counts: Object.fromEntries(
      EVIDENCE_TIERS.map((tier) => [tier, Math.round(row.counts[tier] * factor)]),
    ) as Record<EvidenceTier, number>,
  }))
}

export const EVIDENCE_STATUS_TEXT = {
  text: "Recorded preview fixtures. The evidence summary contract is not connected, so coverage cannot be certified.",
  detail:
    "Counts are fixtures per producer and tier. The chain tab derives its gaps from the local sequence only; no external verification service is called.",
}

/* ---------------------------------------------------------------- filtering */

function matches(text: string, needle: string): boolean {
  return needle === "" || text.toLowerCase().includes(needle)
}

export function filterEvidenceProducers(rows: EvidenceProducerRow[], state: EvidenceFilter): EvidenceProducerRow[] {
  const needle = state.q.toLowerCase()
  return rows.filter(
    (row) =>
      (state.component === "all" || row.id === state.component) &&
      (needle === "" || matches(`${row.label} ${row.service} ${row.note}`, needle)),
  )
}

export function filterTombstones(rows: Tombstone[], state: EvidenceFilter): Tombstone[] {
  const needle = state.q.toLowerCase()
  return rows.filter(
    (row) =>
      (state.basis === "all" || row.basis === state.basis) &&
      (needle === "" ||
        matches(`${row.subjectName} ${row.subjectId} ${row.id} ${row.requestedBy} ${DELETION_BASIS_LABELS[row.basis]}`, needle)),
  )
}

export function filterChainLinks(rows: ChainLink[], state: EvidenceFilter): ChainLink[] {
  const needle = state.q.toLowerCase()
  return rows.filter(
    (row) =>
      (state.chainState === "all" || row.state === state.chainState) &&
      (needle === "" || matches(`${row.producer} ${row.consumer} ${row.kind} ${row.subjectId} ${row.outboxId ?? ""}`, needle)),
  )
}

export type EvidenceFilter = {
  q: string
  component: string
  basis: DeletionBasis | "all"
  chainState: ChainState | "all"
}

export function evidenceProducerLabel(id: string): string {
  return EVIDENCE_PRODUCERS.find((row) => row.id === id)?.label ?? id
}
