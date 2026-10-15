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

The following remain explicitly outside this acceptance: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, production ClickHouse delivery, hosted recovery, and exactly-once effect. PR C adds a reviewed positive-list session metadata sanitizer, an authoritative PostgreSQL session fence lookup, and a proof-gated typed acknowledgement adapter; these are local runtime evidence, not new G0 acceptance. Store validation still checks declarations rather than independently inspecting content. The current chat/session finalizer remains post-response and is not a synchronous durable-before-ack response path; relay delivery remains fail-closed for non-projectable or missing safety metadata.

**Relay deployment boundary:** `packages/evidenceoutbox` is a shared library, not a deployable process; `NewRelay` is called only in tests in this checkout. The pilot is default-disabled by the absence of a runtime daemon, not by an explicit tested feature flag. The PostgreSQL `ibex_evidence_relay` role is `NOLOGIN` and is not granted to `ibex_app`; the package adds no application tenant/agent allowlist or request-auth layer. Row validation and the injected sink fence checker fail closed on unsafe metadata or unavailable fence, but they do not provide deployment gating or authentication. No PostgreSQL `required_evidence` setting exists here. The acknowledgement adapter returns 202 `uncertified` only for an explicitly allowed degraded profile with a matching PostgreSQL proof of retryable outbox state; missing proof, failed, unavailable, and unknown outcomes return 503 `EVIDENCE_UNAVAILABLE`. This adapter is not wired to the post-response chat response, and the asserted `required_evidence=false` relay gate remains unresolved.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| `principal-context.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Contract-shape acceptance recorded 2026-10-10; runtime seam remains provisional | Local/protected profile; AuthService dependency | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No runtime propagation, hosted/HA, or G1 evidence | 2026-11-10 |
| `idempotency-operation.v1` proxy mutation slice | `provisional-with-evidence` | `packages/idempotency/ledger.go`; `packages/idempotency/ledger_test.go`; `services/proxy/internal/http/session_terminate.go`; `services/proxy/internal/http/chat/idempotency.go`; `services/proxy/internal/http/chat/idempotency_ledger_test.go`; migration `infra/migrations/postgres/000043_idempotency_ledger.up.sql` / `.down.sql`; issue #988 | PostgreSQL claim/finalize authority is wired for session termination and non-streaming chat completions when the durable PostgreSQL profile is enabled; chat requires the key, fails closed on ledger errors, and uses the same tenant/agent/key claim contract; focused tests pass | Local/protected proxy profile with PostgreSQL; Redis remains a compatibility fallback only when the durable ledger is disabled; chat is admission-time dedupe and does not claim exactly-once provider execution | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-15 | Full PostgreSQL integration round-trip, shared JCS conformance, reconcile worker, downstream exactly-once, and routes not registered in this proxy remain open; GAP-001 remains open | 2026-11-10 |
| `evidence-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Contract-shape acceptance recorded 2026-10-10; producer sanitizer/fence and acknowledgement adapter are provisional local runtime work | PostgreSQL outbox profile | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No synchronous response-bound acknowledgement, atomic delete-versus-projection fencing, hosted/HA, or production evidence | 2026-11-10 |
| `evidence-relay-sink.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Contract-shape acceptance recorded 2026-10-10; ClickHouse adapter remains a non-production pilot and G4-gated | Local test profile only; PostgreSQL lifecycle authority required | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No cross-store atomic lifecycle fence, production enablement, or hosted/HA recovery evidence | 2026-11-10 |
| `run-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Contract-shape acceptance recorded 2026-10-10; lineage remains design-only | No runtime profile or durable store authorized | Elshaday Mengesha / Rick1330 (Rick acting across all roles; no separate reviewer named) | 2026-10-10 | No runtime type, persistence, replay, or approval-consumption evidence | 2026-11-10 |
| Evidence relay contract hardening | `provisional` | `packages/evidenceoutbox/types.go`; `store.go`; `relay.go`; `relay_unit_test.go`; `store_integration_test.go`; migration `infra/migrations/postgres/000036_evidence_plane.up.sql` | Verified 2026-10-14 after PR #975: Go unit suite passed and all 8 PostgreSQL-backed integration tests passed against the local Podman test DB. One ClickHouse integration test was skipped; the ClickHouse pilot remains locally tested only. | Local Podman PostgreSQL/fake sink plus non-production ClickHouse pilot; production sink remains G4-gated | Evidence/Operations + Platform/Data + Security/Privacy; Rick1330 acting across roles, no separate reviewer named | 2026-10-14 | Producer sanitizer/fence is added in PR C; no cross-store atomic lifecycle fence, production enablement, or hosted/HA recovery evidence. The typed acknowledgement adapter is not bound to the post-response chat response | 2026-11-10 |
| Session evidence producer slice | `provisional-with-evidence` | `services/proxy/internal/http/session/evidence.go`; `services/proxy/internal/http/session/evidence/sanitize.go`; `packages/session/evidence_fence.go`; `packages/evidenceoutbox/reconcile_store.go`; migrations `000041_session_evidence_fence` and `000042_evidence_model_token_metadata`; issue #984 / PR #985 | See **PR C local validation** below for exact package counts and timings; the migration test suite exercises rollback/apply of the new migrations | Local Podman PostgreSQL; session chat finalizer remains post-response; relay pilot is default-disabled | Evidence/Platform + Security/Privacy; Rick1330 acting across roles; no independent reviewer named | 2026-10-14 | Fence lookup and outbox write are separate transactions; sink check+projection is not atomic with deletion; no synchronous response-bound durable-before-ack, production relay, hosted/HA, or exactly-once guarantee. See the versioned sanitizer allowlist at `web/engineering/architecture-v2/contracts/evidence/session-metadata-allowlist-v1.md` | 2026-11-10 |
| GAP-007 historical conflict candidates | `provisional` | `services/memory/app/vectorstore/base.py`; `historical.py`; `pgvector_store.py`; `dedup/service.py`; `conflict/persist.py`; `read/repository.py`; memory unit/integration tests | `make test-memory` passed on 2026-10-14: 484 passed, 88 deselected, 97.58% total coverage (95% gate met). Four PostgreSQL integration modules (23 tests) and Phase 3 HTTP lifecycle E2E were last recorded on 2026-10-08 under PR #943; PR #977 adds the dedicated historical-search capability boundary. | Local PostgreSQL/pgvector + Redis; Phase 3 E2E used stub TEI/Auth/Embedder. Development/test evidence only | Memory + Context; Rick1330 acting across roles, no separate reviewer named | 2026-10-14 (unit suite); PostgreSQL integration/E2E evidence last recorded 2026-10-08 | `HistoricalConflictCapability` requires non-empty org/agent IDs; PostgreSQL search, conflict-candidate load, and supersession updates include both predicates. User reads remain validity-fenced. `SearchMode` remains available to internal code holding a `VectorStore`; continue auditing callers. Typed memory lifecycle/provenance/checkpoints and a durable revision ledger remain unimplemented. The current unit run is not hosted/HA, GDPR/MinIO purge (#641), or stale-cache (#647) evidence | 2026-11-10 |

## PR C local validation (2026-10-14)

- `IBEX_RUNTIME=podman IBEX_NETWORK=host make check`: passed; Markdown lint covered 179 files with 0 issues, gitleaks found no leaks, toolchain versions matched, and all configured stack readiness probes passed.
- `IBEX_RUNTIME=podman IBEX_NETWORK=host make lint-go`: passed all three configured Go lint scopes with 0 issues.
- Focused unit command `go test ./packages/apierror ./packages/evidenceoutbox ./packages/session ./services/proxy/internal/http/session/evidence ./services/proxy/internal/http/session`: 5 packages passed.
- PostgreSQL migration suite `go test -count=1 -tags=integration -race -timeout=300s -p=1 -parallel=1 ./infra/migrations/postgres`: 1 package passed in 94.854s; migration rollback/apply paths, including 000041/000042, passed.
- Focused persistence suite `go test -count=1 -tags=integration -race -timeout=300s -p=1 -parallel=1 ./packages/evidenceoutbox/... ./packages/session`: 3 packages passed (19.384s, 1.021s, and 65.426s).
- Full `IBEX_RUNTIME=podman IBEX_NETWORK=host make test-integration`: 76 package test results passed, 0 failed, and 10 packages reported `[no test files]`; PostgreSQL migrations completed in 122.163s. The first run hit the local wrapper's 120s per-package timeout; the wrapper was raised to 300s without changing test coverage or assertions, and the rerun passed.
- `bash -n infra/scripts/dev-tool.sh` and `git diff --check`: passed. The optional `shellcheck` executable is not installed in this sandbox.

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
