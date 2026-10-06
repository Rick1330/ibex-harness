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

ADR-0084 and issue #933 propose the first G0/G1/G2 contract packet for verified principal propagation, token-bound agent selection, protected-profile verifier readiness, and tenant-bound idempotency semantics. The packet is **proposed**, not accepted: no implementation or local test result may be promoted to `shipped-accepted` until named owners approve the contract, profile assumptions, negative-test evidence, limitations, and review date.

## Ledger template

| Claim | Status | Source | Evidence | Profile | Owner | Verified | Limitations | Review |
|---|---|---|---|---|---|---|---|---|
| Example: protected proxy auth | `shipped-local` | `services/proxy/...` | integration test link | Compose | Proxy owner | YYYY-MM-DD | no HA evidence | YYYY-MM-DD |

## Rules

- Never use `complete`, `production-ready`, or `supported` without a ledger entry.
- Keep target SLOs separate from measured SLOs.
- A benchmark result includes workload, hardware, concurrency, warm/cold state, percentiles, error policy, and artifact/config digests.
- Security and isolation evidence must include negative tests, not only successful requests.
- When a claim expires, downgrade it to `unknown` or `provisional` until reverified.
