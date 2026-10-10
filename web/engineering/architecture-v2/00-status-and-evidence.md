# Status and Evidence Ledger

**Status:** `accepted` for the five G0 contract shapes only; runtime seams remain `provisional` and entries require continuous maintenance.

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

ADR-0084 and original issue #935 (closed; historical context) define the first G0/G1/G2 contract packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, tenant-bound idempotency, evidence acknowledgement/redaction, and relay/sink profile boundaries. On 2026-10-10, Rick1330, acting across all roles, accepted the five contract shapes recorded in the registry. This acceptance freezes contract text and safety semantics only; it does not claim runtime implementation, hosted/HA support, production readiness, or G1-G4 completion.

Issue #955 and PR #956 are the environment-automation chronology. Issue #957 tracks this owner-acceptance documentation change. The exact acceptance artifact is `21-g0-owner-decision-record.md`, including the five resolved questions, owner/date rows, profile defaults, limitations, and review date.

### Owner confirmation log

- **2026-10-09 — provisional owner assignments:** The owner confirmed Rick1330 (acting) across all G0 owner roles.
- **2026-10-09 — standing proposal choices:** The owner confirmed RFC 8785 JCS, version `jcs/v1`; durable-before-ack as the default for evidence-required profiles with typed `uncertified` only under an explicitly permitted degraded profile; ClickHouse as the selected v1 relay sink with its adapter still G4-gated; PostgreSQL resource-lifecycle as the canonical tombstone/version authority; and AuthService-issued immutable `PolicySnapshot` as the authority.
- **2026-10-10 — G0 contract-shape acceptance:** G0 accepted by Rick1330 (acting owner, all roles) on 2026-10-10, review window closed early by owner authorization. Review/expiry is 2026-11-10 or earlier on material profile or authority change.

The acceptance artifact is linked to the exact source commit and evidence bundle. It identifies the local/protected profile, dependencies, authority and trust labels, error/deadline/retry/idempotency/replay/redaction/retention/tombstone semantics, limitations, and review date. Runtime seams remain `provisional` until their required evidence is recorded.

The following remain explicitly outside this acceptance: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, ClickHouse delivery, lifecycle-table integration, hosted recovery, and exactly-once effect. Existing local evidenceoutbox and memory tests remain local evidence only; the current production session producer still supplies neither class nor fence (`services/proxy/internal/http/session/evidence.go:91-118`), so relay delivery remains fail-closed until safe producer metadata is wired.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| `principal-context.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Owner acceptance recorded 2026-10-10; implementation seam is provisional | Local/protected profile; AuthService dependency | Elshaday Mengesha / Rick1330 | 2026-10-10 | No runtime propagation, hosted/HA, or G1 evidence | 2026-11-10 |
| `idempotency-operation.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `03-contract-registry.md` | Owner acceptance recorded 2026-10-10; durable ledger remains unimplemented | Local/protected profile; PostgreSQL authority is proposed, not deployed | Elshaday Mengesha / Rick1330 | 2026-10-10 | No universal ledger, crash/replay, or service migration evidence | 2026-11-10 |
| `evidence-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Owner acceptance recorded 2026-10-10; producer seam is provisional | PostgreSQL outbox profile | Elshaday Mengesha / Rick1330 | 2026-10-10 | No sanitizer, producer metadata, hosted/HA, or acknowledgement certification | 2026-11-10 |
| `evidence-relay-sink.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `10-evidence-contract.md` | Owner acceptance recorded 2026-10-10; ClickHouse adapter remains provisional/G4-gated | Local test profile only; PostgreSQL lifecycle authority required | Elshaday Mengesha / Rick1330 | 2026-10-10 | No ClickHouse adapter, atomic lifecycle fence, or hosted/HA recovery evidence | 2026-11-10 |
| `run-envelope.v1` contract shape | `accepted` | `web/engineering/architecture-v2/21-g0-owner-decision-record.md`; `04-principal-policy-and-run.md` | Owner acceptance recorded 2026-10-10; lineage remains design-only | No runtime profile or durable store authorized | Elshaday Mengesha / Rick1330 | 2026-10-10 | No runtime type, persistence, replay, or approval-consumption evidence | 2026-11-10 |
| Evidence relay contract hardening | `provisional` | `packages/evidenceoutbox/types.go`; `store.go`; `relay.go`; `relay_unit_test.go`; `store_integration_test.go`; migration 000036 unchanged | Verified 2026-10-08: evidenceoutbox unit tests pass; all 7 PostgreSQL integration tests pass against local Podman test DB. Producer class/fence injection, unsafe-class/missing-fence/hook rejection, and persisted poison transition verified. PR #943, commit `b0aa4352ce1f560ca6d6a3d352613b39707f7ba5`. | Local fake sink only; ClickHouse selected for v1 but adapter is G4-gated | Evidence/Operations + Platform/Data + Security/Privacy; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | No payload-content sanitizer/class proof or lifecycle-table/sink atomic fence integration. Current session producer supplies neither class nor fence, so rows default unclassified/fenceless and the relay rejects them; do not enable without safe producer metadata. No ClickHouse adapter, hosted/HA recovery, or G0 acceptance | Owner review due 2026-10-22 |
| GAP-007 historical conflict candidates | `provisional` | `services/memory/app/vectorstore/base.py`; `pgvector_store.py`; `dedup/service.py`; `conflict/persist.py`; `read/repository.py`; memory unit/integration tests | Verified 2026-10-08: full memory unit suite 481 passed, 88 deselected, 97.62% coverage; four PostgreSQL integration modules 23 passed; Phase 3 HTTP lifecycle E2E completed successfully (supersession, status/link, user-read fence and teardown). PR #943, commit `b0aa4352ce1f560ca6d6a3d352613b39707f7ba5`. | Local PostgreSQL/pgvector + Redis; HTTP E2E uses stub TEI/Auth/Embedder | Memory + Context; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | Current user repository explicitly uses `USER_RETRIEVAL`; historical enum is internal call-site control, not a capability boundary, so audit direct callers. Conflict candidate persistence relies on agent-scoped upstream search and has no agent_id guard; the in-memory store has no lifecycle timestamps and ignores mode, so cross-agent negative coverage and backend contract parity remain follow-ups. Typed lifecycle/provenance/checkpoints and owner acceptance remain open; E2E defers #641 GDPR/MinIO purge and reports known #647 stale-cache behavior | Owner review due 2026-10-22 |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
