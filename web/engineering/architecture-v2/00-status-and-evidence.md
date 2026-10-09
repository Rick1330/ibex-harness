# Status and Evidence Ledger

**Status:** `specified` — ledger format; entries require continuous maintenance.

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

ADR-0084 and original issue #935 (closed; historical context) define the first G0/G1/G2 contract packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, tenant-bound idempotency, evidence acknowledgement/redaction, and relay/sink profile boundaries. Owner choices were recorded on 2026-10-08 and are reflected in the registry; the packet remains **proposed**, not accepted. On 2026-10-09, the owner confirmed Rick1330 as provisional acting owner across the listed roles, pending assignment of the actual individual owners by/within the review window ending 2026-10-22; see the dated confirmation below. No implementation or local test result may be promoted to `shipped-accepted` until named owners approve the contract, profile assumptions, negative-test evidence, limitations, and review date.

Issue #935 is closed and PR #936 is merged; both are historical context. Issue #944 was closed by PR #943, squash-merged on 2026-10-09 at commit `1934456`, then reopened on 2026-10-09 solely to track this docs-only cleanup. It does not track G0 owner acceptance: the owner-review deadline remains 2026-10-22 and is recorded in this ledger and ADR-0084. Neither closure nor merge is a G0 acceptance artifact. The packet remains **proposed** until named owners approve the recorded choices, profile, and evidence and the ledger links that decision.

### Owner confirmation log

- **2026-10-09 — provisional owner assignments (not G0 acceptance):** The owner confirmed Rick1330 (acting) across all G0 owner roles. Actual individual role assignments remain pending and must be confirmed before/within the owner-review window ending 2026-10-22.
- **2026-10-09 — standing proposal choices (not G0 acceptance):** The owner confirmed RFC 8785 JCS, version `jcs/v1`; durable-before-ack as the default for evidence-required profiles with a typed `uncertified` fallback only under an explicitly permitted degraded profile; ClickHouse as the selected v1 relay sink, with its adapter still G4-gated; the PostgreSQL resource-lifecycle table as the canonical tombstone/version authority; and an AuthService-issued immutable `PolicySnapshot` as the recommended proposal, pending owner sign-off of its authority and freshness details. These confirmations do not change any `proposed` or `specified` status, accept G0, or authorize a new runtime boundary.

The packet's required acceptance artifact is a dated owner decision linked to the exact source commit and evidence bundle. It must identify the supported deployment profile and required dependencies; freeze authority and trust labels; define errors, deadlines, cancellation, retry, idempotency, replay, redaction, retention, tombstone, and recovery semantics; and list the review/expiry date. A PR merge is not an acceptance artifact.

Until that artifact exists, the following remain blocked as implementation-ready: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, and recovery certification. This draft may carry bounded safety hardening that does not create a new authority boundary: the temporal read fence plus typed write-only conflict mode, protected-profile MCP rate-limit failure mode, and evidence relay's additive producer-classification/fence hooks are partial dispositions only. The memory HTTP lifecycle E2E and seven PostgreSQL evidenceoutbox integration tests now pass locally, including a regression that verifies an unsafe row is durably recorded as poison; this is not gap closure or production acceptance. The current production session producer still supplies neither class nor fence (`services/proxy/internal/http/session/evidence.go:91-118`), so relay delivery would fail closed until safe producer metadata is wired. There is no ClickHouse adapter, lifecycle-table integration, evidence-acknowledgement fix, hosted recovery, or exactly-once effect.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| Evidence relay contract hardening | `provisional` | `packages/evidenceoutbox/types.go`; `store.go`; `relay.go`; `relay_unit_test.go`; `store_integration_test.go`; migration 000036 unchanged | Verified 2026-10-08: evidenceoutbox unit tests pass; all 7 PostgreSQL integration tests pass against local Podman test DB. Producer class/fence injection, unsafe-class/missing-fence/hook rejection, and persisted poison transition verified. PR #943, commit `b0aa4352ce1f560ca6d6a3d352613b39707f7ba5`. | Local fake sink only; ClickHouse selected for v1 but adapter is G4-gated | Evidence/Operations + Platform/Data + Security/Privacy; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | No payload-content sanitizer/class proof or lifecycle-table/sink atomic fence integration. Current session producer supplies neither class nor fence, so rows default unclassified/fenceless and the relay rejects them; do not enable without safe producer metadata. No ClickHouse adapter, hosted/HA recovery, or G0 acceptance | Owner review due 2026-10-22 |
| GAP-007 historical conflict candidates | `provisional` | `services/memory/app/vectorstore/base.py`; `pgvector_store.py`; `dedup/service.py`; `conflict/persist.py`; `read/repository.py`; memory unit/integration tests | Verified 2026-10-08: full memory unit suite 481 passed, 88 deselected, 97.62% coverage; four PostgreSQL integration modules 23 passed; Phase 3 HTTP lifecycle E2E completed successfully (supersession, status/link, user-read fence and teardown). PR #943, commit `b0aa4352ce1f560ca6d6a3d352613b39707f7ba5`. | Local PostgreSQL/pgvector + Redis; HTTP E2E uses stub TEI/Auth/Embedder | Memory + Context; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | Current user repository explicitly uses `USER_RETRIEVAL`; historical enum is internal call-site control, not a capability boundary, so audit direct callers. Conflict candidate persistence relies on agent-scoped upstream search and has no agent_id guard; the in-memory store has no lifecycle timestamps and ignores mode, so cross-agent negative coverage and backend contract parity remain follow-ups. Typed lifecycle/provenance/checkpoints and owner acceptance remain open; E2E defers #641 GDPR/MinIO purge and reports known #647 stale-cache behavior | Owner review due 2026-10-22 |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
