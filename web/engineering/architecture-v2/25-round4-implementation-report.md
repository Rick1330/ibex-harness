# Round 4 Implementation Report

**Repository:** `Rick1330/ibex-harness`  
**Baseline:** `e633e48` (`feat(evidence): add ClickHouse relay sink pilot (#968)`)  
**DCO identity:** Elshaday Mengesha <elishum8@gmail.com>

## Implemented logical PRs

| Issue | Branch | Commit | Implementation and evidence |
|---|---|---|---|
| #969 | `issue-969-g0-status-v2` | `4c6b7b8` | G0/GAP-001–003 contract shape is marked accepted by the dated #21 artifact; runtime GAPs remain open and provisional conditions are preserved. |
| #970 | `issue-970-session-evidence-producer-v2` | `f08c205` | Producer proof is explicit and validated; redaction class and authoritative resource fence are never inferred. Added required/degraded acknowledgement profiles, durable/replay/uncertified/unavailable states, unknown-commit failure, stable HTTP mapping, and golden outcome tests. |
| #971 | `issue-971-jcs-evidence-digest` | `a3d4a8e` | Added RFC 8785-compatible JCS canonicalization, all checked-in vector tests, and wired evidence outbox insert + relay verification to the same `jcs/v1` SHA-256 digest. PostgreSQL JSONB audit and session checkpoint schemes remain separate. |
| #972 | `issue-972-memory-historical-capability-v2` | `ede65c4` | Added an internal historical-conflict capability that constructs the privileged mode and asserts organization + agent fences; near-duplicate search uses it and cross-tenant negative coverage remains. |
| #973 | `issue-973-contract-packet-v2` | `1da3c21` | Added the six proposed G1–G7 contract registrations with owner, compatibility, scope/trust, failure/retry, idempotency, privacy/lifecycle, tests, evidence, and non-closure fields. |

## Validation evidence

- `go test ./packages/canonicaljson`: **passed**, including every vector in `contracts/jcs-test-vectors.json` and malformed/duplicate-key rejection.
- `go test ./packages/evidenceoutbox`: **passed**, including JCS digest validation, relay poison/failure/replay behavior, tenant predicates, and producer proof checks.
- `go test ./services/proxy/internal/http/session`: **passed**, including durable, failed-required, unknown, replay, and degraded-profile acknowledgement cases.
- Memory focused suite (`test_dedup_service.py`, `test_inmemory_vectorstore.py`): **25 passed**.
- Baseline repository `make check`: **passed** with Podman readiness probes before the implementation branches were created.

## A2 boundaries

The asynchronous legacy `PersistEvidence` path remains fail-open because it runs after the chat response is committed. Synchronous evidence-required callers must use `PersistEvidenceForProfile`; failed or unknown commits map to `503 SERVICE_DEGRADED` unless the operation explicitly allows `uncertified`. Replay is success but is not reported as a new commit. The producer must provide `ProducerMetadata`; the relay rejects incomplete or unclassified proof.

No lifecycle table/view was found in the current producer path, so no tombstone authority was fabricated. The authoritative fence integration remains a required follow-up migration, not an inferred session/resource ID.

## A3 boundary

Evidence payload digests now use `jcs/v1`. This does **not** replace PostgreSQL `jsonb::text` used by the privacy-audit store or `encoding/json` used by session/checkpoint hashing. The maintained `github.com/cyberphone/json-canonicalization` dependency is covered by the complete repository vector suite.

## A4 boundary

Historical search is routed through a narrow internal adapter for the dedup write path and validates both tenant fences at the capability boundary. The lower-level vector-store substrate remains internal and unchanged for compatibility; typed memory revision ledgers, CAS/idempotency, lifecycle provenance, and migrations remain Round 5 work.

## Phase B boundary

The contract packet is specification-only. No runtime provider manifest, Responses adapter, memory ledger migration, MCP server, console UI, production ClickHouse enablement, hosted/HA certification, or GAP closure is claimed.

## Remaining Round 5 work

1. Budget reservation ledger and operation-authority migration.
2. Provider manifest implementation and provenance governance.
3. `responses.v1` adapter and semantic SSE vectors.
4. Durable typed memory revision ledger with CAS/idempotency and recovery migration.
5. Read-only MCP gateway enforcement surface.
6. Console D1 server-only read-model binding.
7. Authoritative lifecycle fence table integration and required-profile HTTP handler integration.
8. Production ClickHouse sink gate and replay/failover tests.
