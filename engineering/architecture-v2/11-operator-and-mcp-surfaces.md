# Operator and MCP Surfaces

**Status:** `provisional` for current mounted surfaces; target contract below.

## Operator surface

The versioned management API is the authority-facing boundary. Console/BFF is the canonical operator client. Dashboard is compatibility-only. No UI writes databases directly.

Privileged actions—policy/directive promotion, token/key changes, provider credential changes, export, deletion, review/promotion, and rollback—require explicit permission/role, freshness, approval/MFA where required, idempotency, and durable evidence.

Readiness and diagnostics distinguish healthy, degraded, blocked, and uncertified. They do not expose secrets or cross-tenant existence.

### Directive version semantics (`operator.directives.versions.v1`)

The console reads directives through one pointer and one history, and the two are never merged:

- **The pointer.** `directives.active_version_id` names the version a *new* session resolves to. A rollback moves the
  pointer; it does not create a version, so the live version may be older than the newest one. This is the same model
  Langfuse uses for prompt labels and OpenAI uses for a published prompt ID: one mutable reference at immutable
  versions.
- **The history.** `directive_versions` is append-only (a trigger rejects `UPDATE`), numbered monotonically per
  directive, and each row carries a content hash and size. `sessions.directive_version_id` records the version a
  session actually resolved when it started, so an older version can keep serving traffic after a rollback. That is the
  expected shape, not drift.
- **One directive per agent.** `directives` is unique on `agent_id`, so the surface is an agent-to-instruction view, not a library of
  named prompts. A second instruction for the same agent is a new version, not a second directive.
- **What is not in the contract.** Instruction text, diffs, and promotion history. Text is the operator's instruction
  payload; exposing it needs its own contract behind `OPERATOR_REDACTED_READ`. Promotion history needs a write path
  with step-up, CSRF, and an audit record, and the console has none.

The surface reports the two facts separately ("live now" versus "served sessions in the window") so a rollback is
visible instead of being smoothed into a single "current version" number.

### Time reference in the console (two clocks, one boundary)

The console renders relative ages from two different references, and mixing them is a correctness defect, not a style
choice:

- **Preview fixtures** are measured against the fixed `GOVERN_NOW`. A fixture must render the same string on the server
  and the client, and it must not drift as the repository ages.
- **Live surfaces** are measured against a reference they own: the `observed_at` the read returned (stable across SSR and
  immune to client clock skew), or a ticking `nowMs` where the age must keep moving ("last active 12s ago").

`formatGovernRelative` therefore takes a **required** reference, and `RelativeTime` a required `now`. There is no default
because there is no correct one: inheriting the fixture clock on a live page reports a record from today as "just now"
once the constant is behind real time. `tests/clock-boundary.test.ts` enforces the boundary by rejecting `GOVERN_NOW` in
any file that is not under a preview surface or the fixture library.

### Memory lineage (`operator.memories.v1` detail)

The memory plane records why a memory is no longer current, and the operator detail reads it without reading content:

- **Direct replacement.** `memories.superseded_by` and `merged_into` are the row-level answer.
- **Chain head.** `tip` comes from `resolve_supersession_tip(org, memory, 5)`, which walks incoming `supersedes` edges
  in SQL with a depth cap and a cycle break. The walk is not re-implemented in Python, so the cap and the cycle rule
  have one owner. A memory with no successor is its own head.
- **Edges.** `memory_relationships` is typed (`supersedes`, `contradicts`, `specializes`, `generalizes`, `merged_from`,
  `derived_from`) and carries confidence. `replaces` is the out-edge set (what this memory replaced); `replaced_by` is
  the in-edge set (what replaced it). Both are capped at 20 with `edges_truncated`.
- **The other end's state.** Each edge joins `memories` for `status` and `tombstoned`, so a replacement that was later
  deleted reads as "deleted · tombstoned" instead of looking like a live link.

`resolution_notes` is never projected: it is free text adjacent to memory content. Retention follows the same principle
as Graphiti (invalidated facts are kept and marked, not deleted) and Mem0 (a per-memory change history exists); this
contract is the reader for the history we already store.

## MCP surface

MCP is an external resource/tool boundary. It derives scope from authenticated principal, uses versioned tool descriptors and hashes, caps input/output, validates arguments, supports deadlines/cancellation, requires idempotency for writes, and records policy/evidence IDs. Tool descriptions and results are untrusted data.

Read-only tools precede write tools. Production stdio is disabled unless an explicit deployment profile and risk review enable it. MCP is not the identity provider; OAuth/IdP responsibility is documented at the deployment boundary.

### Read-only operator gateway (local, default-off)

`services/mcp-operator` (ADR-0086, issue #1013) mounts a Streamable HTTP MCP surface at `/mcp` only when `IBEX_MCP_OPERATOR_ENABLED=true`. It exposes four `read_only` tools — `session.get`, `run.get`, `evidence.query`, `budget.get` — each mapped to one typed scope over the existing permission bitmap (`operator.read`, `runs.read`, `evidence.read`, `budget.read`). Enforcement is shared with `packages/mcp_gateway` in this order: org rate limit → resolve tool → authorize → validate args → timed read → redact → audit. Rate limiting runs first so malformed or unauthorized calls cannot bypass the org budget; unknown or under-scoped calls therefore consume budget.

Identity is token-derived only; tool schemas reject unknown arguments, so callers cannot supply `org_id` or agent identity. Reads run as `ibex_app` with `app.current_org_id` bound and an explicit `org_id` predicate; cross-tenant or missing rows return `not_found`, not `permission_denied`. Output is metadata-only (schema allowlist plus sensitive-key deny-list). Audit is metadata-only and non-blocking; durable rich-field audit is deferred.

Known limitation: Resource/action PolicySnapshot evaluation is not wired (no Python verifier). Authorization is a bitmap check behind a `PolicyEvaluator` seam. This keeps GAP-009 open and must not be read as policy-store enforcement or hosted operator readiness.
