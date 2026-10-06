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
| Current profile scope | Development Compose only, selected by the task owner on 2026-10-06 for local integration | Not a production-support claim; the Compose profile has not been executed in this Sandbox because no container runtime/daemon is available. |
| DecisionService/GLiNER | `design-intent` | No runtime, contract, benchmark, registry, or acceptance evidence exists. |
| Graph/A2A/marketplace/sandbox | `deferred` | These are not current dependencies. |

## G0 review packet

ADR-0084 and issue #935 proposed an initial G0/G1/G2 packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, tenant-bound idempotency, evidence acknowledgement/redaction, and relay/sink profile boundaries. PR #936 closed issue #935, but that closure did **not** record G0 owner acceptance. The packet remains **proposed, not accepted**. The task owner selected **Development Compose only for local integration, with no production-support claim**, on 2026-10-06; this records D0 scope only and does not complete G0. The expanded eight-area source audit and docs-only preparation are tracked by [issue #939](https://github.com/Rick1330/ibex-harness/issues/939); see the [70-criterion synthesis and workplan](20-pre-g0-gap-synthesis-and-workplan.md), the [proposal-only owner decision worksheet](21-g0-owner-decision-recommendations.md), and the [source-audit index](../research/ibex-preflight-2026-10/README.md). No implementation or local test result may be promoted to `shipped-accepted` until named auth/policy, contract, evidence/security, and deployment owners approve the contract, profile assumptions, negative-test evidence, limitations, and review date.

The required acceptance artifact is a dated owner decision linked to the exact source commit and evidence bundle. It must identify the supported deployment profile and required dependencies; freeze authority and trust labels; define errors, deadlines, cancellation, retry, idempotency, replay, redaction, retention, tombstone, and recovery semantics; resolve the open budget/provider/memory/context/MCP/session/evidence choices in the synthesis; and list limitations and the review/expiry date. A PR merge or issue closure is not an acceptance artifact.

Until that artifact exists, the following remain blocked as implementation-ready: repo-wide `PrincipalContext`/`RunEnvelope` migration, durable budget reservation, provider manifest/adapters, typed memory lifecycle, MCP governance, control-plane effects, and recovery certification. On target `main` `7298e5ee7982b926630566c88830c99650c8eb37`, PRs #934 and #936 contain bounded hardening: token-bound agent-selection/verifier readiness, memory temporal retrieval predicates with a separate historical conflict-candidate mode, protected-profile MCP Redis failure behavior, and evidence payload-digest/ack-loss replay checks. These remain **partial** dispositions, not gap closure or production acceptance. In particular, relay digest/replay tests do not establish required-before-ack timing, a deployed sink, tombstone fencing, hosted recovery, or exactly-once external effects. PR #937 changes search-index CI/deploy size synchronization only and supplies no evidence for these architecture gaps.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |
| PostgreSQL relay digest/replay hardening | `provisional` | `packages/evidenceoutbox/relay.go` and relay tests; PR #936 (`125fde3da214649f319cb54e5f87b96f2ed3575c`) | focused digest validation and PostgreSQL ack-loss/replay integration test (DB availability required) | local PostgreSQL integration profile | Evidence/Security + Platform; pending named reviewer | 2026-10-06 audit of target `main` | no accepted G0, deployed sink, tombstone fence, arbitrary-input redaction, hosted/HA, or recovery certification | owner review required |
| Historical conflict candidates | `provisional` | `services/memory/app/dedup/service.py`, vector search request/SQL contract; PR #936 (`125fde3da214649f319cb54e5f87b96f2ed3575c`) | focused request-mode and SQL predicate regression tests; hosted Phase 3 integration acceptance not established by this ledger | memory PostgreSQL/pgvector write profile | Memory + Context; pending named reviewer | 2026-10-06 audit of target `main` | default user-retrieval temporal fence remains; typed lifecycle and profile acceptance remain open | owner review required |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
