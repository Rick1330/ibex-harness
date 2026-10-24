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

export const capabilities: Capability[] = [
  {
    name: 'Auth and proxy foundations',
    status: 'IMPLEMENTED',
    detail: 'PAT and agent validation, permission bitmap, tenant-scoped middleware, policy snapshots, and fail-closed admission paths. Local evidence only.',
    href: '/docs/security/authentication',
  },
  {
    name: 'Management API',
    status: 'IMPLEMENTED',
    detail: 'Local organization, user, agent, token, provider credential, model policy, and rate-limit configuration APIs with tenant-scoped tests.',
    href: '/docs/api-reference/management-api',
  },
  {
    name: 'Rate limiting',
    status: 'IMPLEMENTED',
    detail: 'Hierarchical Redis sliding-window limits with organization and agent scope, runtime configuration, and outage behavior. Hosted HA remains open.',
    href: '/docs/proxy/rate-limiting',
  },
  {
    name: 'Provider routing and fallback',
    status: 'IMPLEMENTED',
    detail: 'OpenAI, Anthropic, OpenAI-compatible, and mock adapters; per-organization chains; circuit breakers; fallback headers. No hosted conformance matrix.',
    href: '/docs/proxy/provider-adapters',
  },
  {
    name: 'Memory substrate',
    status: 'IMPLEMENTED',
    detail: 'PostgreSQL and pgvector storage, dedup, conflict candidates, temporal reads, and a Redis hot cache. Typed lifecycle and deletion certification remain open.',
    href: '/docs/memory/overview',
  },
  {
    name: 'Context assembly',
    status: 'PROVISIONAL',
    detail: 'Budget, retrieval, ranking, packing, formatting, and degradation exist. Caller authentication and the deadline boundary remain open.',
    href: '/docs/context/overview',
  },
  {
    name: 'Extraction workers',
    status: 'PROVISIONAL',
    detail: 'Batch extraction and a cassette-backed evaluation harness exist. Queue durability, live model quality, and exactly-once projection are not certified.',
    href: '/docs/intelligence/extraction',
  },
  {
    name: 'MCP memory tools',
    status: 'PROVISIONAL',
    detail: 'Search, write, and feedback tools exist. Audit is logging-first rather than evidence-grade.',
    href: '/docs/mcp/memory-server',
  },
  {
    name: 'MCP operator gateway',
    status: 'IMPLEMENTED',
    detail: 'Read-only metadata tools ship locally and default-off. PolicySnapshot resource evaluation, durable audit, and hosted support remain open.',
    href: '/docs/mcp/operator-gateway',
  },
  {
    name: 'Streaming hardening',
    status: 'PROVISIONAL',
    detail: 'SSE forwarding, draining, and provider error normalization exist. Slow-client, bounded-buffer, leak, and long-running soak evidence remains open.',
    href: '/docs/proxy/provider-routing-and-resilience',
  },
  {
    name: 'Budget, usage, and cost',
    status: 'PROVISIONAL',
    detail: 'Durable hard-cap holds, rate cards, usage queries, and reconciliation foundations exist. Extraction usage export and full reconciliation remain open.',
    href: '/docs/proxy/idempotency-and-budgets',
  },
  {
    name: 'Evidence plane',
    status: 'PROVISIONAL',
    detail: 'Outbox, default-off relay, fence checks, and a ClickHouse pilot exist. The sink is not a production acknowledgement authority.',
    href: '/docs/operations/evidence-and-relay',
  },
  {
    name: 'Operator Console · live reads',
    status: 'PROVISIONAL',
    detail: 'Canonical shell plus live overview and metadata-only trace exploration. No login, token issuance, mutations, or hosted two-tenant evidence.',
    href: '/docs/operations/console',
  },
  {
    name: 'Operator Console · workflows',
    status: 'DEFERRED',
    detail: 'Sessions, replay, incidents, evidence bundles, directives, actions, drift, cost views, and settings remain fixture-only or deferred.',
    href: '/docs/operations/console',
  },
  {
    name: 'Production operations and recovery',
    status: 'PROPOSED',
    detail: 'Helm, API ingress, restore drills, and release gates are partially prepared. No production origin, passing RPO target, or E1–E4 evidence.',
    href: '/docs/deployment/production-readiness',
  },
  {
    name: 'DecisionService and GLiNER',
    status: 'PROPOSED',
    detail: 'Design intent only. No runtime, contract, benchmark, registry, or acceptance evidence exists.',
    href: '/docs/architecture/status-and-evidence',
  },
  {
    name: 'Graph, A2A, marketplace, sandbox',
    status: 'DEFERRED',
    detail: 'Not current dependencies. Requires a separate gate, evidence, and ADR.',
    href: '/docs/architecture/status-and-evidence',
  },
]

export interface Gate {
  id: string
  title: string
  status: Status
  summary: string
  evidence: string
}

export const gates: Gate[] = [
  {
    id: 'G0',
    title: 'Documentation and contract freeze',
    status: 'PROVISIONAL',
    summary: 'Five contract shapes accepted 2026-10-10. Runtime seams remain provisional.',
    evidence: 'Review/expiry 2026-11-10. Acting owner across all roles; no independent reviewer named.',
  },
  {
    id: 'G1',
    title: 'Principal and tenant invariants',
    status: 'PROVISIONAL',
    summary: 'Propagation, RLS, cache/search/analytics isolation, anti-enumeration, and fail-closed tests.',
    evidence: 'Contract shape accepted; runtime propagation and cross-tenant matrix remain open.',
  },
  {
    id: 'G2',
    title: 'Errors and idempotency',
    status: 'PROVISIONAL',
    summary: 'Transport mappings, body hashes, claim/finalize/replay/TTL/crash behavior.',
    evidence: 'PostgreSQL ledger evidence exists for bounded proxy, worker, and memory paths. Reconciliation and broader coverage remain open.',
  },
  {
    id: 'G3',
    title: 'Provider and admission',
    status: 'PROVISIONAL',
    summary: 'Immutable manifests, token fit, reservations, limits, reconciliation, no-provider-after-deny.',
    evidence: 'Adapters and budget holds exist locally. Hosted and reconciliation evidence remains open.',
  },
  {
    id: 'G4',
    title: 'Evidence MVP',
    status: 'PROVISIONAL',
    summary: 'Envelope, outbox, relay, dedupe/replay, redaction, retention, restore, event coverage.',
    evidence: 'Local outbox and default-off relay evidence. Production sink and hosted recovery remain open.',
  },
  {
    id: 'G5',
    title: 'Request and streaming slice',
    status: 'PROVISIONAL',
    summary: 'One measured provider path, separate Responses semantics, stable errors, accepted latency budget.',
    evidence: 'Local slice exists. No hosted/reference p99 run is published.',
  },
  {
    id: 'G6',
    title: 'Typed memory and context',
    status: 'PROVISIONAL',
    summary: 'Provenance, trust, PII/quarantine, operation status, deletion tombstone, typed manifest, fallback.',
    evidence: 'Memory substrate is locally evidenced. Typed lifecycle, revision ledger, and deletion certification remain open.',
  },
  {
    id: 'G7',
    title: 'Read-only operator and MCP',
    status: 'PROVISIONAL',
    summary: 'Versioned API, Console, diagnostics, read-only MCP, descriptor hashes, limits, stdio policy.',
    evidence: 'Read-only gateway shipped locally, default-off. Policy-store enforcement and durable audit remain open.',
  },
  {
    id: 'G8',
    title: 'Operations and recovery',
    status: 'PROVISIONAL',
    summary: 'Profiles, backups, restore, migrations, drain, capacity, incidents, key rotation, measured RPO/RTO.',
    evidence: 'Local operational building blocks exist. Hosted/HA recovery and restore drills remain open.',
  },
  {
    id: 'G9',
    title: 'Governed side effects',
    status: 'PROPOSED',
    summary: 'Operation intent/receipt, approval, exact tool descriptors, egress, credentials, isolated execution.',
    evidence: 'Specified only. No runtime or acceptance evidence.',
  },
  {
    id: 'G10',
    title: 'Advisory intelligence',
    status: 'PROPOSED',
    summary: 'Benchmark, pin, calibrate, shadow, canary, rollback, resource and isolation gates. No model authority.',
    evidence: 'Specified only. DecisionService and model registry do not exist.',
  },
  {
    id: 'G11',
    title: 'Deferred extensions',
    status: 'DEFERRED',
    summary: 'Graph, A2A, managed cloud, marketplace, broad guardrails, coding sandbox, extra providers.',
    evidence: 'Requires separate evidence and ADR.',
  },
]

export interface Gap {
  id: string
  priority: 'P0' | 'P1' | 'P2'
  title: string
  disposition: 'Open' | 'Partial'
  detail: string
}

export const gaps: Gap[] = [
  {
    id: 'GAP-001',
    priority: 'P0',
    title: 'Cross-document status and claim conflicts',
    disposition: 'Partial',
    detail: 'PostgreSQL claim/finalize paths exist for bounded proxy, worker, and memory writes. Management API, reconciliation, retention, and hosted evidence remain open.',
  },
  {
    id: 'GAP-002',
    priority: 'P0',
    title: 'Runtime authority propagation and budgets',
    disposition: 'Partial',
    detail: 'RS256 policy snapshots and typed failures exist locally. Budget enforcement, context propagation, async continuation, and hosted evidence remain open.',
  },
  {
    id: 'GAP-003',
    priority: 'P0',
    title: 'Incomplete route, proto, event, and MCP registry',
    disposition: 'Open',
    detail: 'Five G0 shapes and six proposals are registered. Remaining public and runtime surfaces are not complete.',
  },
  {
    id: 'GAP-004',
    priority: 'P0',
    title: 'Unmeasured latency SLOs',
    disposition: 'Partial',
    detail: 'p99 ≤20 ms is a ratified warm target, not a measured hosted SLO. The PR-time Go gate is mean-based. No recent passing full-chat p99 run is published.',
  },
  {
    id: 'GAP-005',
    priority: 'P0',
    title: 'Tenant isolation, deletion, and evidence not proven end-to-end',
    disposition: 'Open',
    detail: 'Response-bound durable acknowledgement, atomic delete-versus-projection fencing, production deployment, and full-store coverage remain open.',
  },
  {
    id: 'GAP-006',
    priority: 'P0',
    title: 'Reservation, idempotency, and reconciliation not accepted',
    disposition: 'Partial',
    detail: 'Bounded PostgreSQL holds exist for hard-cap periods. Crash/replay, cross-language canonicalization, reconciliation, and hosted evidence remain open.',
  },
  {
    id: 'GAP-007',
    priority: 'P1',
    title: 'Typed memory lifecycle and revision ledger',
    disposition: 'Open',
    detail: 'Historical candidate search and temporal reads are fenced. Durable typed lifecycle, provenance, checkpoints, and revision ledger remain unimplemented.',
  },
  {
    id: 'GAP-008',
    priority: 'P1',
    title: 'Provider alias, capability, streaming, and usage semantics',
    disposition: 'Open',
    detail: 'Capability manifest and conformance matrix remain open.',
  },
  {
    id: 'GAP-009',
    priority: 'P1',
    title: 'MCP and operator boundary mixed',
    disposition: 'Partial',
    detail: 'Read-only gateway exists locally and default-off. PolicySnapshot resource/action evaluation, descriptor re-verification, durable audit, and hosted support remain open.',
  },
  {
    id: 'GAP-010',
    priority: 'P1',
    title: 'DecisionService, registry, calibration, benchmark do not exist',
    disposition: 'Open',
    detail: 'Keep design-intent and gate at G10.',
  },
  {
    id: 'GAP-011',
    priority: 'P1',
    title: 'Backup, restore, migration, incident, and operator evidence incomplete',
    disposition: 'Partial',
    detail: 'A default-off relay and local fence evidence exist. Production sink, request auth, tenant allowlist, hosted recovery, and restore drills remain open.',
  },
  {
    id: 'GAP-012',
    priority: 'P2',
    title: 'Graph, A2A, marketplace, sandbox, and broad provider expansion',
    disposition: 'Open',
    detail: 'Deferred until core gates pass.',
  },
]

export const evidenceFacts = [
  { label: 'G0 contract shapes', value: '5', note: 'accepted 2026-10-10' },
  { label: 'Open gaps', value: '12', note: '6 partial, 6 open' },
  { label: 'Published p99 SLO', value: '—', note: 'no hosted/reference run' },
  { label: 'License', value: 'MIT', note: 'self-hosted source' },
]
