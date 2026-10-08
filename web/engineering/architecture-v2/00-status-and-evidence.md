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

ADR-0084 and issue #935 define the first G0/G1/G2 contract packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, tenant-bound idempotency, evidence acknowledgement/redaction, and relay/sink profile boundaries. Owner choices were recorded on 2026-10-08 and are reflected in the registry; the packet remains **proposed**, not accepted. Rick1330 is acting across the listed owner roles pending individual confirmation during the 14-day review window ending 2026-10-22. No implementation or local test result may be promoted to `shipped-accepted` until named owners approve the contract, profile assumptions, negative-test evidence, limitations, and review date.

Issue #935 is closed and PR #936 is merged; a follow-up hardening PR is being prepared and will be linked here and in the issue comments. Neither closure nor merge is a G0 acceptance artifact. The packet remains proposed until named owners confirm the recorded choices, profile and evidence, and the ledger links that review.

The packet's required acceptance artifact is a dated owner decision linked to the exact source commit and evidence bundle. It must identify the supported deployment profile and required dependencies; freeze authority and trust labels; define errors, deadlines, cancellation, retry, idempotency, replay, redaction, retention, tombstone, and recovery semantics; and list the review/expiry date. A PR merge is not an acceptance artifact.

Until that artifact exists, the following remain blocked as implementation-ready: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, and recovery certification. This draft may carry bounded safety hardening that does not create a new authority boundary: the temporal read fence plus typed write-only conflict mode, protected-profile MCP rate-limit failure mode, and evidence relay's additive producer-classification/fence hooks are partial dispositions only. The memory HTTP lifecycle E2E and six PostgreSQL evidenceoutbox integration tests now pass locally; this is not gap closure or production acceptance. The current production session producer still supplies neither class nor fence (`services/proxy/internal/http/session/evidence.go:91-118`), so relay delivery would fail closed until safe producer metadata is wired. There is no ClickHouse adapter, lifecycle-table integration, evidence-acknowledgement fix, hosted recovery, or exactly-once effect.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| Evidence relay contract hardening | `provisional` | `packages/evidenceoutbox/types.go`; `store.go`; `relay.go`; `relay_unit_test.go`; `store_integration_test.go`; migration 000036 unchanged | Verified 2026-10-08: evidenceoutbox unit tests pass; all 6 PostgreSQL integration tests pass against local Podman test DB. Producer class/fence injection and unsafe-class/missing-fence/hook rejection verified. PR #943, commit `2965797a27b2ae8cb2ebaface3bbb465f852982f`. | Local fake sink only; ClickHouse selected for v1 but adapter is G4-gated | Evidence/Operations + Platform/Data + Security/Privacy; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | No payload-content sanitizer/class proof or lifecycle-table/sink atomic fence integration. Current session producer supplies neither class nor fence, so rows default unclassified/fenceless and the relay rejects them; do not enable without safe producer metadata. No ClickHouse adapter, hosted/HA recovery, or G0 acceptance | Owner review due 2026-10-22 |
| GAP-007 historical conflict candidates | `provisional` | `services/memory/app/vectorstore/base.py`; `pgvector_store.py`; `dedup/service.py`; `conflict/persist.py`; `read/repository.py`; memory unit/integration tests | Verified 2026-10-08: full memory unit suite 480 passed, 88 deselected, 97.56% coverage; four PostgreSQL integration modules 23 passed; Phase 3 HTTP lifecycle E2E completed successfully (supersession, status/link, user-read fence and teardown). PR #943, commit `2965797a27b2ae8cb2ebaface3bbb465f852982f`. | Local PostgreSQL/pgvector + Redis; HTTP E2E uses stub TEI/Auth/Embedder | Memory + Context; Rick1330 acting, individual confirmation due 2026-10-22 | Branch `feature/IBEX-935-g0-contract-packet-completion`; base `c0872d0c9638f4221af99778a5a2f915ff3a0228` | Current user repository explicitly uses `USER_RETRIEVAL`; historical enum is internal call-site control, not a capability boundary, so audit direct callers. Typed lifecycle/provenance/checkpoints and owner acceptance remain open; E2E defers #641 GDPR/MinIO purge and reports known #647 stale-cache behavior | Owner review due 2026-10-22 |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
