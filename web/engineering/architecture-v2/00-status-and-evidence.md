# Status and Evidence Ledger

**Status:** Five G0 contract shapes are `accepted` as of 2026-10-10 by Rick1330 (acting owner across all roles); the accepted scope is contract text and safety semantics only. Runtime seams remain `provisional`. No independent reviewer is named in the decision record. Review/expiry is 2026-11-10, or earlier on a material profile or authority change.

## Claim rule

A claim becomes `shipped-accepted` only when the ledger contains:

- Source entry point and commit.
- Test, benchmark, recovery drill, or hosted-acceptance artifact.
- Deployment profile and dependency assumptions.
- Owner and verification date.
- Known limitations and review/expiry date.

## Current baseline

| Area | Current documented status | What must not be inferred |
|---|---|---|
| Auth/proxy foundations | `shipped-local` / profile-dependent | Not proof of hosted HA or measured proxy SLO. |
| Provider/tokenizer packages | `shipped-local` / adapter-dependent | A model name is not a capability contract. |
| Memory substrate | `shipped-local` | Not proof of typed projections, deletion certification, or production isolation. |
| Context assembly | `provisional` | The caller-authentication limitation and deadline discrepancy remain open. |
| Extraction workers | `provisional` | Queue durability and exactly-once projection effects are not certified. |
| MCP memory tools | `provisional` | Logging-only audit is not evidence-grade audit. |
| Management API/Console | `provisional` | Mounted routes are not production operator readiness. |
| DecisionService/GLiNER | `design-intent` | No runtime, contract, benchmark, registry, or acceptance evidence exists. |
| Graph/A2A/marketplace/sandbox | `deferred` | These are not current dependencies. |

## G0 review packet

ADR-0084 and original issue #935 (closed; historical context) define the first G0/G1/G2 contract packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, tenant-bound idempotency, evidence acknowledgement/redaction, and relay/sink profile boundaries. On 2026-10-10, Rick1330, acting across all roles, accepted the five contract shapes recorded in the registry. This freezes contract text and safety semantics only; it does not claim runtime implementation, hosted/HA support, production readiness, or G1-G4 completion.

Issue #955 and PR #956 are the environment-automation chronology. Issue #957 tracks the owner-acceptance documentation change. The exact acceptance artifact is `21-g0-owner-decision-record.md`; it records the decision date, acting assignment, local/protected profile defaults, limitations, and 2026-11-10 review date. No separate independent reviewer is named there.

### Owner confirmation log

- **2026-10-09 — provisional owner assignments:** The owner confirmed Rick1330 (acting) across all G0 owner roles.
- **2026-10-09 — standing proposal choices:** The owner confirmed RFC 8785 JCS, version `jcs/v1`; durable-before-ack as the default for evidence-required profiles with typed `uncertified` only under an explicitly permitted degraded profile; ClickHouse as the selected v1 relay sink with its adapter still G4-gated; PostgreSQL resource-lifecycle as the canonical tombstone/version authority; and AuthService-issued immutable `PolicySnapshot` as the authority.
- **2026-10-10 — G0 contract-shape acceptance:** G0 accepted by Rick1330 (acting owner, all roles); the review window closed early by owner authorization. Review/expiry is 2026-11-10 or earlier on material profile or authority change.

The acceptance artifact is the authority for accepted contract-shape decisions. It identifies the local/protected profile, dependencies, authority and trust labels, error/deadline/retry/idempotency/replay/redaction/retention/tombstone semantics, limitations, and review date. Runtime seams remain `provisional` until their required evidence is recorded.

The following remain explicitly outside this acceptance: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, production ClickHouse delivery, lifecycle-table integration, hosted recovery, and exactly-once effect. Evidence producer types can carry `RedactionClass`, `TombstoneFence`, and `ProducerMetadata`; the current production chat/session path does not supply that metadata. Store validation checks the supplied proof metadata and matching fence fields, but does not inspect or sanitize payload content. The session's deferred persistence is post-response and is not a synchronous durable-before-ack path; relay delivery remains fail-closed for missing safety metadata.

**Relay deployment boundary:** `packages/evidenceoutbox` is a shared library, not a deployable process; `NewRelay` is called only in tests in this checkout. The pilot is default-disabled by the absence of a runtime daemon, not by an explicit tested feature flag. The PostgreSQL `ibex_evidence_relay` role is `NOLOGIN` and is not granted to `ibex_app`; the package adds no application tenant/agent allowlist or request-auth layer. Row validation and the injected sink fence checker fail closed on unsafe metadata or unavailable fence, but they do not provide deployment gating or authentication. No PostgreSQL `required_evidence` setting exists here. The helper's zero-value `EvidenceAckProfile.Required=false` returns `uncertified` (HTTP 200) on persistence failure, not fail-closed; the task's asserted `required_evidence=false` gate remains unresolved.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| `principal-context.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Contract-shape acceptance recorded 2026-10-10; runtime seam remains provisional | Local/protected profile; AuthService dependency | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No runtime propagation, hosted/HA, or G1 evidence | 2026-11-10 |
| `idempotency-operation.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `03-contract-registry.md` | Contract-shape acceptance recorded 2026-10-10; durable ledger remains unimplemented | Local/protected profile; PostgreSQL authority is proposed, not deployed | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No universal ledger, crash/replay, or service migration evidence | 2026-11-10 |
| `evidence-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Contract-shape acceptance recorded 2026-10-10; producer/acknowledgement runtime remains provisional | PostgreSQL outbox profile | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No reviewed payload-content sanitizer, session producer metadata wiring, synchronous acknowledgement certification, hosted/HA, or production evidence | 2026-11-10 |
| `evidence-relay-sink.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Contract-shape acceptance recorded 2026-10-10; ClickHouse adapter remains a non-production pilot and G4-gated | Local test profile only; PostgreSQL lifecycle authority required | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No cross-store atomic lifecycle fence, production enablement, or hosted/HA recovery evidence | 2026-11-10 |
| `run-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Contract-shape acceptance recorded 2026-10-10; lineage remains design-only | No runtime profile or durable store authorized | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No runtime type, persistence, replay, or approval-consumption evidence | 2026-11-10 |
| Evidence relay contract hardening | `provisional` | `packages/evidenceoutbox/types.go`; `store.go`; `relay.go`; `relay_unit_test.go`; `store_integration_test.go`; migration `infra/migrations/postgres/000036_evidence_plane.up.sql` | Verified 2026-10-14 after PR #975: Go unit suite passed and all 8 PostgreSQL-backed integration tests passed against the local Podman test DB. One ClickHouse integration test was skipped; the ClickHouse pilot remains locally tested only. | Local Podman PostgreSQL/fake sink plus non-production ClickHouse pilot; production sink remains G4-gated | Evidence/Operations + Platform/Data + Security/Privacy; Rick1330 acting across roles, no separate reviewer named | 2026-10-14 | The production session path still supplies neither class nor fence; metadata validation is not content sanitization; the typed acknowledgement helper is not wired to a synchronous response boundary. No cross-store atomic lifecycle fence, production enablement, or hosted/HA recovery evidence | 2026-11-10 |
| GAP-007 historical conflict candidates | `provisional` | `services/memory/app/vectorstore/base.py`; `historical.py`; `pgvector_store.py`; `dedup/service.py`; `conflict/persist.py`; `read/repository.py`; memory unit/integration tests | `make test-memory` passed on 2026-10-14: 484 passed, 88 deselected, 97.58% total coverage (95% gate met). Four PostgreSQL integration modules (23 tests) and Phase 3 HTTP lifecycle E2E were last recorded on 2026-10-08 under PR #943; PR #977 adds the dedicated historical-search capability boundary. | Local PostgreSQL/pgvector + Redis; Phase 3 E2E used stub TEI/Auth/Embedder. Development/test evidence only | Memory + Context; Rick1330 acting across roles, no separate reviewer named | 2026-10-14 (unit suite); PostgreSQL integration/E2E evidence last recorded 2026-10-08 | `HistoricalConflictCapability` requires non-empty org/agent IDs; PostgreSQL search, conflict-candidate load, and supersession updates include both predicates. User reads remain validity-fenced. `SearchMode` remains available to internal code holding a `VectorStore`; continue auditing callers. Typed memory lifecycle/provenance/checkpoints and a durable revision ledger remain unimplemented. The current unit run is not hosted/HA, GDPR/MinIO purge (#641), or stale-cache (#647) evidence | 2026-11-10 |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
