# GAP-007 Memory Lifecycle v1 (Draft)

**Status:** `draft` / `provisional` — not accepted, shipped, or production-ready.

**Decision status:** Proposed for implementation review. GAP-007 remains open. This document does not update the contract registry's status for the G1–G7 proposals.

**Authority source:** `web/engineering/architecture-v2/21-g0-owner-decision-record.md:22,59-61`. The G0 owner decision assigns canonical memory lifecycle authority to the memory service and its PostgreSQL resource-lifecycle record, with the PostgreSQL data layer providing the transactionally checked fence. This draft implements that assigned authority; it does not accept the new lifecycle contract surface.

## Problem

The Python memory service reads `deleted_at` as a search/conflict predicate but currently has no user-facing per-memory forget mutation. Worker extraction reads session eligibility once and later sends independent memory HTTP writes. Those writes carry no session lifecycle revision. The gap is a check-then-write boundary, not evidence that the current code can resurrect an already-forgotten memory: a per-memory forget path is not present in the current implementation.

## Proposed lifecycle authority and revision fence

The memory service's PostgreSQL record is canonical for each memory lifecycle. It carries a monotonically increasing `bigint` revision, tombstone state, and optional `expires_at`. Lifecycle-changing operations compare an expected revision and advance it atomically with their mutation. Forget records a tombstone and advances the revision. A tombstone is terminal for ordinary mutation and indexing; no stale request may clear or bypass it.

Extraction also carries the expected lifecycle revision of the source session that it observed as eligible. The memory service validates, inside the same PostgreSQL transaction as each session-backed mutation, that the source session is present in the same organization, completed/eligible, not deleted, and still at the expected session revision; it takes `SELECT ... FOR UPDATE` on that session row. Migration `000045` adds a database trigger that advances the session revision on status, deletion, organization, or agent changes. A forget of a session-linked memory advances that same source-session fence in its transaction, so writes and progress updates captured before the forget fail closed. A mismatch, missing source, or ineligible session produces `STALE_LIFECYCLE_REVISION` and no partial memory, label, supersession, or lifecycle-event write. A changed supersession/PII target has the distinct `STALE_MEMORY_REVISION` code; extraction treats that target race as retryable and reloads candidates on a fresh task attempt, while a stale source session remains non-retryable. The worker carries the observed revision through each HTTP write and its progress-pointer update. This is a local implementation of the owner-assigned shared-PostgreSQL authority boundary, not an accepted lifecycle-contract surface.

The memory row mutation and its lifecycle outbox event commit in one PostgreSQL transaction. Outbox failure rolls back the mutation; mutation failure leaves no event. Events contain identifiers and lifecycle metadata only, never memory content, embeddings, or unredacted PII. Memory mutations acquire the same transaction-scoped organization advisory lock as the deletion saga and reject writes once an organization is cancelled. The purge statement emits events from the exact rows returned by its `DELETE`, atomically with that deletion.

## Lifecycle event schema and delivery

Proposed additive event envelope, with a versioned schema:

| Field | Meaning |
|---|---|
| `schema_version` | Integer schema version, initially `1`. |
| `memory_id` | Canonical memory identifier. |
| `org_id` | Tenant identifier, derived from verified scope and stored for tenant-safe delivery. |
| `revision` | Monotonic memory revision produced by the committed mutation. |
| `event_type` | Typed lifecycle transition, such as `created`, `content_updated`, `superseded`, `forgotten`, `expired`, or `purged`. |
| `occurred_at` | Server/database timestamp for the committed transition. |

The payload is deliberately redacted: it contains only the fields above and any separately reviewed non-content lifecycle metadata required for delivery. It must not include memory body, prompt, embedding, token, or unredacted PII.

**Transport decision for this draft:** Use the dedicated `ibex_core.memory_lifecycle_outbox` in migration `000045`; do not repurpose `packages/evidenceoutbox`, whose aggregate remains run-request-keyed. The table has one normalized, redacted row per `(org_id, memory_id, revision)`, tenant RLS, pending/lease metadata, and least-privilege application/service grants. A future relay can claim available undelivered rows with an ordered `FOR UPDATE SKIP LOCKED` lease query, publish to a separately registered lifecycle consumer contract, then acknowledge by row ID and tenant scope. That poll/lease/ack relay and every downstream consumer are **not implemented or subscribed** in this slice; no delivery guarantee or consumer behavior is claimed.

## Mutations, retrieval, and retention

- Add `POST /v1/memories/{memory_id}/forget`, requiring `memory:write` plus an agent-scoped token. Org and agent come only from verified token context. The JSON body requires `expected_revision` (positive `BIGINT`); success returns `{data:{memory_id,revision,tombstoned:true}}`. Lifecycle-domain errors are `403 AGENT_SCOPE_REQUIRED`, `404 NOT_FOUND`, and `409 STALE_LIFECYCLE_REVISION`. The complete HTTP contract also includes `401 MISSING_TOKEN`, `403 INSUFFICIENT_PERMISSIONS`, `422` for invalid UUID/body/revision validation, `503 SERVICE_DEGRADED` for unavailable authentication, and `503 DATABASE_UNAVAILABLE`. It compares the expected memory revision, advances revision, tombstones the row, clears embeddings, advances the source-session fence when present, and emits the event atomically.
- Supersede and other lifecycle-changing mutations use revision guards. A concurrent forget/supersede conflict has one committed winner; the losing stale operation receives the typed stale-revision error and no partial effects.
- Vector upsert carries an expected memory revision and updates only a same-org, matching-revision, non-tombstoned row. Vector deletion requires a matching revision, affects only non-tombstoned rows, clears embedding fields, and fails closed on a missing/stale/tombstoned row. All search modes exclude tombstoned rows.
- `expires_at` is a soft-expiry fence for ordinary retrieval, not automatic erasure. Historical/export access is separately authorized, explicitly scoped, and still cannot expose tombstoned rows. No general historical/export access is created by this proposal.
- Asynchronous purge is deferred while an applicable legal hold is active. Organization deletion must record purge events from exactly the rows actually deleted in the same PostgreSQL statement/transaction; the shared advisory lock prevents concurrent memory creation from crossing the purge boundary. Held data must not be purged.

## Compatibility and migration

- Existing memory rows are initialized to lifecycle revision `1`; nondeleted rows start with `tombstoned = false`, while legacy `status = 'deleted'` or non-null `deleted_at` rows are reconciled to `tombstoned = true` without incrementing their initial revision or making them visible. The migration must be reversible where safe and refuse rollback once tombstones or other lifecycle state exist.
- `expires_at` is nullable for existing rows. No expiration is inferred from validity-window fields or cache TTL.
- Reads remain compatible when clients omit an expected revision, subject to existing authentication and tenant checks. Lifecycle-changing writes that cannot establish a required expected revision fail closed with a typed error; there is no silent un-fenced legacy-write fallback. Worker API rollout must coordinate sender and receiver versions so an old worker does not continue writing without a fence.
- The forget endpoint's authentication scope, tenant derivation, request preconditions, response shape, and typed errors must be documented in the API specification and contract registry before claiming a supported public API.

## Verification and remaining evidence

### Local implementation verification (2026-10-17)

These are local Sandbox results for the unreviewed implementation, not acceptance, shipment, hosted-support, or production evidence:

- Memory service: `uv run ruff check app tests/unit tests/integration` passed; `uv run pytest -q tests/unit` passed (488 tests); the full real-PostgreSQL integration suite passed (73 passed, 22 skipped). The focused lifecycle/PII set passed (9 tests) after adding the failed-mutation/no-event, content-update event, and forget/supersede race regressions.
- Worker service: `uv run ruff check app tests` passed; the complete unit and integration suite passed (439 passed, 2 skipped) against local PostgreSQL 16 and Redis 7.0.15. Real-PostgreSQL tests exercise purge-event persistence and active legal-hold deferral.
- PostgreSQL migration package: `go test -race -tags=integration ./infra/migrations/postgres -count=1` passed. Migration tests include `ibex_app` outbox RLS, terminal tombstones, clean 000045 rollback, and refusal after lifecycle state exists.
- Repository gates: `make repo-guards`, `make lint-docs`, and `IBEX_TEST_MODE=1 make check-tools` passed. Gitleaks directory scan examined approximately 36.27 MB and found no leaks.

Some environment-gated integration tests remain skipped. No all-services Compose/HA/hosted test, object-store or ClickHouse deletion proof, lifecycle relay/subscriber, independent review, or owner acceptance is claimed. GAP-007 remains open pending review and explicit acceptance.

### Remaining evidence and boundaries

The implementation must retain regressions for stale extraction versus forget, concurrent supersede versus forget, mutation/outbox rollback in both directions, soft-expiry visibility, tombstone exclusion from every search mode, stale/tombstoned vector-upsert refusal and cleared embeddings, `ibex_app` tenant RLS, purge-event persistence, and legal-hold deferral. The above local PostgreSQL suites exercise these requested lifecycle paths; skipped tests and external-service/hosted profiles remain unverified. A known boundary remains: privileged/manual direct SQL can advance the database revision trigger without emitting an outbox event; supported lifecycle mutations must use the memory service transaction helpers, and DB-level event completeness is not yet enforced. `expired` is a reserved event type with no producer; expiration currently acts only as a soft retrieval gate. These boundaries require review before contract acceptance.

## Explicit non-claims

This remains a provisional draft, not an accepted lifecycle contract, an accepted/shipped feature, or production/HA certification. It does not claim that current code had prevented resurrection before this unreviewed implementation, that a resurrection has occurred, or that a consumer is subscribed. No GAP-007 closure or status promotion is authorized by this draft. Any unresolved authority, transaction-boundary, compatibility, retention, or transport decision must be surfaced rather than inferred.
