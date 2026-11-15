export type Status = 'IMPLEMENTED' | 'PROVISIONAL' | 'PROPOSED' | 'DEFERRED' | 'UNKNOWN'

export interface StatusMeta {
  label: string
  ledgerClass: string
  description: string
}

export const statusMeta: Record<Status, StatusMeta> = {
  IMPLEMENTED: {
    label: 'Implemented',
    ledgerClass: 'shipped-local',
    description: 'Implemented and locally evidenced. Not a claim of hosted, HA, or production readiness.',
  },
  PROVISIONAL: {
    label: 'Provisional',
    ledgerClass: 'provisional',
    description: 'A runtime seam or contract exists, but required evidence, review, or a gate remains open.',
  },
  PROPOSED: {
    label: 'Proposed',
    ledgerClass: 'design-intent',
    description: 'Specified or designed only. No runtime, benchmark, or acceptance evidence is claimed.',
  },
  DEFERRED: {
    label: 'Deferred',
    ledgerClass: 'deferred',
    description: 'Intentionally outside the current dependency set and gated behind a later decision.',
  },
  UNKNOWN: {
    label: 'Unknown',
    ledgerClass: 'unknown',
    description: 'The claim expired or the evidence is missing. Treat it as unverified.',
  },
}

export interface Capability {
  name: string
  status: Status
  detail: string
  href: string
}

/**
 * One capability row. The field names are stated once, in this labelled tuple,
 * instead of on every entry: the data is positional and `capabilities` rebuilds
 * the objects from it.
 */
type CapabilityRow = readonly [name: string, status: Status, detail: string, href: string]

const capabilityRows: readonly CapabilityRow[] = [
  ['Auth and proxy foundations', 'IMPLEMENTED', 'PAT and agent validation, permission bitmap, tenant-scoped middleware, policy snapshots, and fail-closed admission paths. Local evidence only.', '/docs/security/authentication'],
  ['Management API', 'IMPLEMENTED', 'Local organization, user, agent, token, provider credential, model policy, and rate-limit configuration APIs with tenant-scoped tests.', '/docs/api-reference/management-api'],
  ['Rate limiting', 'IMPLEMENTED', 'Hierarchical Redis sliding-window limits with organization and agent scope, runtime configuration, and outage behavior. Hosted HA remains open.', '/docs/proxy/rate-limiting'],
  ['Provider routing and fallback', 'IMPLEMENTED', 'OpenAI, Anthropic, OpenAI-compatible, and mock adapters; per-organization chains; circuit breakers; fallback headers. No hosted conformance matrix.', '/docs/proxy/provider-adapters'],
  ['Memory substrate', 'IMPLEMENTED', 'PostgreSQL and pgvector storage, dedup, conflict candidates, temporal reads, and a Redis hot cache. Typed lifecycle and deletion certification remain open.', '/docs/memory/overview'],
  ['Embedding model identity', 'PROVISIONAL', 'The embedding identity is recorded on every embedded row and configurable: the model id, plus the revision appended as @revision (for example bge-m3@r1) when IBEX_MEMORY_EMBEDDING_MODEL_REVISION is set, so two revisions of one model id cannot share an identity. The search fence must be given that full string and is off by default. It bounds only the vector channel: the full-text channels are not fenced, so a keyword hit recorded under another generation can still be returned. No re-embed path exists — the only embedding task is a no-op, and there is no generation column or backfill task. Licence and model-revision fields are still unrecorded in the inventory for every model; BAAI/bge-m3 carries a weights revision only in the v1-single-node Compose file. The dev bundle runs deterministic stub geometry at an overridden dimension, so this is a configuration record, not a semantic-quality claim.', '/docs/architecture/status-and-evidence'],
  ['Context assembly', 'PROVISIONAL', 'Budget, retrieval, ranking, packing, formatting, and degradation exist. Unauthenticated direct access is closed by a shared caller token; per-user authentication and the deadline boundary remain open.', '/docs/context/overview'],
  ['Ranking-quality benchmarks', 'PROVISIONAL', 'The published v1 gold set is twenty saturated queries, so its 1.0 scores measure corpus difficulty rather than ranking quality. The v2 mode comparison cannot separate graph suppression from reranking: full_graph equals hybrid_rerank because the expected memory must outrank the twin that suppression removes, so the removed document cannot move nDCG@10. No v2 number is published.', '/docs/intelligence/evaluation'],
  ['Extraction workers', 'PROVISIONAL', 'Batch extraction and a cassette-backed evaluation harness exist. Queue durability, live model quality, and exactly-once projection are not certified.', '/docs/intelligence/extraction'],
  ['MCP memory tools', 'PROVISIONAL', 'Search, write, and feedback tools exist. Audit is logging-first rather than evidence-grade.', '/docs/mcp/memory-server'],
  ['MCP operator gateway', 'IMPLEMENTED', 'Read-only metadata tools ship locally and default-off. PolicySnapshot resource evaluation, durable audit, and hosted support remain open.', '/docs/mcp/operator-gateway'],
  ['Streaming hardening', 'PROVISIONAL', 'SSE forwarding, draining, and provider error normalization exist. Slow-client, bounded-buffer, leak, and long-running soak evidence remains open.', '/docs/proxy/provider-routing-and-resilience'],
  ['Budget, usage, and cost', 'PROVISIONAL', 'Durable hard-cap holds, rate cards, usage queries, and reconciliation foundations exist. Extraction usage export and full reconciliation remain open.', '/docs/proxy/idempotency-and-budgets'],
  ['Evidence plane', 'PROVISIONAL', 'Outbox, default-off relay, fence checks, and a ClickHouse pilot exist. The sink is not a production acknowledgement authority.', '/docs/operations/evidence-and-relay'],
  ['Operator Console · live reads', 'PROVISIONAL', 'Canonical shell plus live overview, platform health, metadata-only trace exploration, the agent inventory, the memory index, the session ledger, the evidence summary, and the directive version timeline: 8 of 10 core surfaces (ADR-0089). Browser exposure is limited to the non-secret NUXT_PUBLIC_IBEX_ENV label; credentials and upstream origins stay in the server-only BFF. No login, token issuance, mutations, or hosted two-tenant evidence.', '/docs/operations/console'],
  ['Operator Console · preview tiers', 'DEFERRED', '2 core surfaces and 8 platform-tier surfaces remain preview designs. Labelled illustrative fixtures are permitted under ADR-0089 §4; no live claim is made.', '/docs/operations/console'],
  ['v1-single-node profile', 'IMPLEMENTED', 'One Compose project starts every required service behind an edge TLS terminator with one published port, digest-pinned dependencies, and a safe one-time identity bootstrap. Three one-shot gates run in order: migrate, provision, then bootstrap. Every application service connects on its capability login and every long-running service refuses to start on the owner or a superuser — ibex_bootstrap, ibex_auth, ibex_runtime (proxy, api, memory) and ibex_worker; only migrate and provision use the owner credential. Live-proven on 2026-11-15: all 13 health-checked containers healthy, no application connection is ibex, an unpinned cross-tenant read on ibex_runtime raises 42501, and a route-level cross-tenant request returns 403. That is a live cross-tenant read plus the integration suites, not a full acceptance suite. Hosted/HA operation, multi-user auth, a measured p99 SLO, a two-tenant browser journey, and a recovery drill remain open.', '/docs/deployment/v1-single-node'],
  ['Production operations and recovery', 'PROPOSED', 'Helm, API ingress, restore drills, and release gates are partially prepared. No production origin, passing RPO target, or E1–E4 evidence.', '/docs/deployment/production-readiness'],
  ['DecisionService and GLiNER', 'PROPOSED', 'Design intent only. No runtime, contract, benchmark, registry, or acceptance evidence exists.', '/docs/architecture/status-and-evidence'],
  ['Graph, A2A, marketplace, sandbox', 'DEFERRED', 'Not current dependencies. Requires a separate gate, evidence, and ADR.', '/docs/architecture/status-and-evidence'],
]

export const capabilities: Capability[] = capabilityRows.map(
  ([name, status, detail, href]) => ({ name, status, detail, href }),
)

export interface Gate {
  id: string
  title: string
  status: Status
  summary: string
  evidence: string
}

/** One gate row, positional: [id, title, status, summary, evidence]. */
type GateRow = readonly [id: string, title: string, status: Status, summary: string, evidence: string]

const gateRows: readonly GateRow[] = [
  ['G0', 'Documentation and contract freeze', 'PROVISIONAL', 'Five contract shapes accepted 2026-10-10; four re-verified 2026-11-06, one lapsed 2026-11-10 and renewed 2026-11-11. Runtime seams remain provisional.', 'Review/expiry 2027-02-06 for all five shapes. idempotency-operation.v1 was not re-verified on 2026-11-06, lapsed on 2026-11-10 with no decision recorded, and was renewed by the owner on 2026-11-11 to the same date on the 2026-11-09 evidence packet plus the additive 409 IDEMPOTENCY_KEY_ERASED term (engineering/architecture-v2/33-idempotency-shape-lapse-record-2026-11-11.md). The nine provisional runtime rows were re-verified 2026-11-09 and carry 2027-02-06. Acting owner across all roles; no independent reviewer named. See the 2026-11-06 G0 review record.'],
  ['G1', 'Principal and tenant invariants', 'PROVISIONAL', 'Propagation, RLS, cache/search/analytics isolation, anti-enumeration, and fail-closed tests.', 'Contract shape accepted; runtime propagation and cross-tenant matrix remain open.'],
  ['G2', 'Errors and idempotency', 'PROVISIONAL', 'Transport mappings, body hashes, claim/finalize/replay/TTL/crash behavior.', 'PostgreSQL ledger evidence exists for bounded proxy, worker, and memory paths. Reconciliation and broader coverage remain open.'],
  ['G3', 'Provider and admission', 'PROVISIONAL', 'Immutable manifests, token fit, reservations, limits, reconciliation, no-provider-after-deny.', 'Adapters and budget holds exist locally. Hosted and reconciliation evidence remains open.'],
  ['G4', 'Evidence MVP', 'PROVISIONAL', 'Envelope, outbox, relay, dedupe/replay, redaction, retention, restore, event coverage.', 'Local outbox and default-off relay evidence. Production sink and hosted recovery remain open.'],
  ['G5', 'Request and streaming slice', 'PROVISIONAL', 'One measured provider path, separate Responses semantics, stable errors, accepted latency budget.', 'Local slice exists. No hosted/reference p99 run is published.'],
  ['G6', 'Typed memory and context', 'PROVISIONAL', 'Provenance, trust, PII/quarantine, operation status, deletion tombstone, typed manifest, fallback.', 'Memory substrate is locally evidenced. Typed lifecycle, revision ledger, and deletion certification remain open.'],
  ['G7', 'Read-only operator and MCP', 'PROVISIONAL', 'Versioned API, Console, diagnostics, read-only MCP, descriptor hashes, limits, stdio policy.', 'Read-only gateway shipped locally, default-off. Policy-store enforcement and durable audit remain open.'],
  ['G8', 'Operations and recovery', 'PROVISIONAL', 'Profiles, backups, restore, migrations, drain, capacity, incidents, key rotation, measured RPO/RTO.', 'Local operational building blocks exist. Hosted/HA recovery and restore drills remain open.'],
  ['G9', 'Governed side effects', 'PROPOSED', 'Operation intent/receipt, approval, exact tool descriptors, egress, credentials, isolated execution.', 'Specified only. No runtime or acceptance evidence.'],
  ['G10', 'Advisory intelligence', 'PROPOSED', 'Benchmark, pin, calibrate, shadow, canary, rollback, resource and isolation gates. No model authority.', 'Specified only. DecisionService and model registry do not exist.'],
  ['G11', 'Deferred extensions', 'DEFERRED', 'Graph, A2A, managed cloud, marketplace, broad guardrails, coding sandbox, extra providers.', 'Requires separate evidence and ADR.'],
]

export const gates: Gate[] = gateRows.map(
  ([id, title, status, summary, evidence]) => ({ id, title, status, summary, evidence }),
)

export interface Gap {
  id: string
  priority: 'P0' | 'P1' | 'P2'
  title: string
  disposition: 'Open' | 'Partial'
  detail: string
}

/** One gap row, positional: [id, priority, title, disposition, detail]. */
type GapRow = readonly [id: string, priority: Gap['priority'], title: string, disposition: Gap['disposition'], detail: string]

const gapRows: readonly GapRow[] = [
  ['GAP-001', 'P0', 'Cross-document status and claim conflicts', 'Partial', 'PostgreSQL claim/finalize paths exist for bounded proxy, worker, and memory writes. Management API, reconciliation, retention, and hosted evidence remain open.'],
  ['GAP-002', 'P0', 'Runtime authority propagation and budgets', 'Partial', 'RS256 policy snapshots and typed failures exist locally. Budget enforcement, context propagation, async continuation, and hosted evidence remain open.'],
  ['GAP-003', 'P0', 'Incomplete route, proto, event, and MCP registry', 'Open', 'Five G0 shapes and six proposals are registered. Remaining public and runtime surfaces are not complete.'],
  ['GAP-004', 'P0', 'Unmeasured latency SLOs', 'Partial', 'p99 ≤20 ms is a ratified warm target, not a measured hosted SLO. The PR-time Go gate is mean-based. No recent passing full-chat p99 run is published.'],
  ['GAP-005', 'P0', 'Tenant isolation, deletion, and evidence not proven end-to-end', 'Open', 'Response-bound durable acknowledgement, atomic delete-versus-projection fencing, production deployment, and full-store coverage remain open.'],
  ['GAP-006', 'P0', 'Reservation, idempotency, and reconciliation not accepted', 'Partial', 'Bounded PostgreSQL holds exist for hard-cap periods. Crash/replay, cross-language canonicalization, reconciliation, and hosted evidence remain open.'],
  ['GAP-007', 'P1', 'Typed memory lifecycle and revision ledger', 'Open', 'Historical candidate search and temporal reads are fenced. Durable typed lifecycle, provenance, checkpoints, and revision ledger remain unimplemented.'],
  ['GAP-008', 'P1', 'Provider alias, capability, streaming, and usage semantics', 'Open', 'Capability manifest and conformance matrix remain open.'],
  ['GAP-009', 'P1', 'MCP and operator boundary mixed', 'Partial', 'Read-only gateway exists locally and default-off. PolicySnapshot resource/action evaluation, descriptor re-verification, durable audit, and hosted support remain open.'],
  ['GAP-010', 'P1', 'DecisionService, registry, calibration, benchmark do not exist', 'Open', 'Keep design-intent and gate at G10.'],
  ['GAP-011', 'P1', 'Backup, restore, migration, incident, and operator evidence incomplete', 'Partial', 'A default-off relay and local fence evidence exist. Production sink, request auth, tenant allowlist, hosted recovery, and restore drills remain open.'],
  ['GAP-012', 'P2', 'Graph, A2A, marketplace, sandbox, and broad provider expansion', 'Open', 'Deferred until core gates pass.'],
]

export const gaps: Gap[] = gapRows.map(
  ([id, priority, title, disposition, detail]) => ({ id, priority, title, disposition, detail }),
)

/** One evidence fact row, positional: [label, value, note]. */
type EvidenceFactRow = readonly [label: string, value: string, note: string]

const evidenceFactRows: readonly EvidenceFactRow[] = [
  ['G0 contract shapes', '5', 'accepted 2026-10-10'],
  ['Open gaps', '12', '6 partial, 6 open'],
  ['Published p99 SLO', '—', 'no hosted/reference run'],
  ['License', 'MIT', 'self-hosted source'],
]

export const evidenceFacts = evidenceFactRows.map(([label, value, note]) => ({ label, value, note }))
