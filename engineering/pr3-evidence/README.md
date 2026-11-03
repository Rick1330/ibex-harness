# PR-3 readiness evidence

**Baseline:** `main@1a1b89f` (2026-09-26)

This directory records source-level PR-3 bootstrap contracts and separates them from evidence that requires an authorized staging or GitHub administrator action.

## Status vocabulary

| Status | Meaning |
|---|---|
| `specified` | Contract is documented but not implemented. |
| `implemented` | Code or configuration exists in the repository. |
| `contract-tested` | Deterministic local tests exercise the contract. |
| `runtime-tested` | A real dependency-backed runtime exercised it. |
| `staging-verified` | The canonical staging topology produced immutable evidence. |
| `live-GitHub-verified` | An authorized owner checked live branch protection. |
| `blocked` | The repository cannot produce the evidence without an external owner or environment. |
| `accepted-residual-risk` | A named owner accepted the risk with an expiry, mitigation, and rollout restriction. |

## Current decision record

| Area | Current status | Owner/action required |
|---|---|---|
| PR #897 fail-closed Proxy behavior | `implemented`, local-tested | Hosted CI and staging Redis outage/provider non-invocation evidence remain required. |
| PR #900 session/JWT lifecycle | `implemented`, contract-tested | AuthService + Redis + PostgreSQL runtime, browser, and tenant-negative evidence remain required. |
| Legal-hold high-impact browser path | `blocked` | Decide whether to migrate the route to operator sessions or approve a separately governed PAT automation contract. |
| Canonical topology | `implemented`, `blocked` for runtime closure | Provision DNS/Ingress/TLS, secret delivery, and SSE proxy behavior. |
| Canonical console fixture boundary | `implemented`, `contract-tested` | Browser no-fixture, accessibility, visual, and compatibility evidence remain. |
| P6-bootstrap | `implemented` when this PR's schema/parser/manifest checks pass | Staging E2E and live branch-protection parity remain external. |
| Live branch protection | `declared` in `.github/branch-protection-main.json` | Authorized GitHub owner must apply and verify contexts and review policy. |

## D1-entry decision

| Blockers to start D1 | Blockers to complete D1 | Later-slice/release blockers |
|---|---|---|
| P0 runtime topology and environment proof; P1 mounted/runtime auth evidence; D0 no-fixture and quality evidence; P6-bootstrap manifest/parser/check parity; unsafe residuals restricted by owner. | Real context/Overview/health/SSE contracts; four-role/two-tenant browser journeys; freshness/partial/degraded states; URL state; rollback and accessibility evidence. | P2 trace/read-model completeness; P3 raw-content/lifecycle guarantees; P4 reconciliation/cost governance; P5 PITR/RPO/RTO/Kyverno; E1-E4 release evidence. |

## External blockers

The repository must not claim closure until these are attached to the same immutable revision/environment identity:

- hosted CI/analyzer results for the PR head;
- live GitHub branch-protection parity and approving-review policy;
- AuthService/Redis/PostgreSQL cross-replica and RLS runtime evidence;
- DNS/Ingress/TLS and SSE proxy verification;
- external secret-manager ownership, rotation, and staging values;
- authenticated staging browser smoke and rollback transcript;
- PITR/RPO/RTO, Kyverno, chaos/load, and Track E evidence.
