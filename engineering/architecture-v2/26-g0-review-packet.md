# G0 Owner Review Packet (2026-11-10)

**Title:** G0 review packet — audit reconciliation, evidence status, and the decisions the owner still owes.
**Description:** Review input for the 2026-11-10 G0 review. Maps the eight source-audit clusters onto `GAP-001`–`GAP-012` and G0–G11, classifies every material claim by evidence status, records post-acceptance changes, and enumerates the unresolved owner decisions with W0–W9 work packages. It accepts nothing.
**Audience:** The G0 owner (Elshaday Mengesha / @Rick1330), the acting reviewers for each G0 role, and any agent beginning work under the architecture-v2 packet.
**Status:** Review input only. Not an acceptance, not a status promotion, not a gap closure.
**Base:** `main` at `5a032466` (2026-11-05). **Packet date:** 2026-11-05.
**Review/expiry:** 2026-11-10 (`21-g0-owner-decision-record.md:7,84`, as those lines read when this packet was written; both now point forward to 2027-02-06). **Performed 2026-11-06**, four days early, because ADR-0097 selected a supported profile (a material profile change); the outcome is [`28-g0-review-record-2026-11-06.md`](28-g0-review-record-2026-11-06.md). This packet is left as the input it was.

> **Citation legend.** Bare `NN-*.md:LINE` references are files in `engineering/architecture-v2/`. `adr/NNNN` is
> `engineering/adr/NNNN-*.md`. Paths beginning `new findings/` are the gitignored, untracked audit scratch at the
> repository root: they are provenance for this packet, not repository content, and are excluded from markdownlint.

## 1. What this packet is

On 2026-10-10 Rick1330, acting across all G0 roles, accepted five G0 **contract shapes** — principal binding, policy
freshness, idempotency, evidence publication, and privacy/deletion — and left every runtime seam `provisional`
(`21-g0-owner-decision-record.md:3,15-24,78`). The record schedules the next review for 2026-11-10
(`21-g0-owner-decision-record.md:7`). Since then, eight independent audit/research documents were produced in
`new findings/`, five runtime slices merged, and the Console became the only operator application. None of that has
been reconciled against the accepted decisions in one place. This is that reconciliation.

It does **not** accept G0, promote a ledger row, close a gap, or authorise runtime work. See §7.

## 2. Cluster reconciliation

Each audit cluster is mapped to its canonical register entry and to the gate that governs it
(`17-roadmap-and-gates.md:7-18`). "Current status" is the status **recorded** in the controlling documents at
`5a032466`; "Verified delta" is what I re-checked in the tree and is developed in §3.

| # | Cluster and source | What the audit claimed | GAP | Gate | Current recorded status | Verified delta at `5a032466` |
|---|---|---|---|---|---|---|
| C1 | Full-stack cross-cutting (`new findings/Full-Stack Engineering Audit_ Cross-Cutting Gaps Before Phase 4 Track D.md:9-11`, pinned `5d7e0f21`) | Provider secrets readable without `OrgSettingsWrite`; BYO BaseURL SSRF; startup-only readiness; tool/formatter overhead outside context budget; ignored rank weights; lossy packer repair | `GAP-001`, `GAP-002`, `GAP-004`, `GAP-005`, `GAP-008` | G1, G2, G3, G6 | GAP-002 partial (`18-gap-register.md:8`), GAP-006 partial (`18-gap-register.md:12`), GAP-004 open (`00-status-and-evidence.md:70`), GAP-005 open (`18-gap-register.md:11`) | **Narrowed, not closed.** Credential `Get` now requires `permissions.SecretUse` and SSRF-validates the stored BaseURL (`services/auth/internal/grpc/provider_credentials.go:63-81`); `/ready` now performs live per-request dependency checks (`services/api/app/probes.py:19-31`); context budget now subtracts tool-schema serialization and formatter overhead (`services/context/app/budget.py:3,51,73,100-102,164`). Rank-weight/half-life wiring and the packer repair path were **not** re-checked. |
| C2 | World-class cross-cutting (`new findings/World-Class Cross-Cutting Audit_  Before Track D.md:9-13`, pinned `5d7e0f21`) | Model policy fails **open** without Postgres; lossy policy Pub/Sub invalidation; best-effort revocation; org deletion cleans Postgres only; SSE write deadline cleared; no backup/restore evidence; Python CI gate not protected | `GAP-002`, `GAP-005`, `GAP-008`, `GAP-011` | G1, G2, G4, G8 | GAP-002 partial (`18-gap-register.md:8`), GAP-005 open (`18-gap-register.md:11`), GAP-011 partial (`18-gap-register.md:17`), production ops `design-intent`/partial (`00-status-and-evidence.md:35`) | **Partially narrowed.** `PassthroughRegistry` no longer exists at head (0 hits; present at the audit revision at `services/proxy/internal/bootstrap/postgres.go:353` in `5d7e0f21`). `ci-gate-python` is now a required check (`.github/branch-protection-main.json:9`). SSE deadline still cleared (`services/proxy/internal/http/stream_forward.go:86`). Revocation, dual-write, deletion, backup: **not re-run**. |
| C3 | Policy snapshot slice (`new findings/IBEX-997-gap-002-policy-snapshot-report.md:36-63`) | AuthService-issued, RS256-signed `policy-snapshot.v1` verified fail-closed in the proxy, with typed `SNAPSHOT_*` errors | `GAP-002` | G0 shape → G1/G2 runtime | `provisional` (`00-status-and-evidence.md:77`); `implemented-local` in `03-contract-registry.md:54` | **Confirms the decision, leaves the gap open.** Package, issuer, verifier, key set, middleware and tests exist (`packages/policysnapshot/`, `services/auth/internal/grpc/policy_snapshot.go`, `services/proxy/internal/http/policy_snapshot_middleware.go`). No key-revocation propagation, no async-continuation class, no context hop. |
| C4 | Budget reservations (`new findings/IBEX-1000-gap-006-budget-reservation-ledger-report.md:14-41`) | Hard-cap admission enforced against a cached rollup; durable tenant-scoped hold ledger with lease reaping and bounded overshoot | `GAP-006` | G3 | `provisional` (`00-status-and-evidence.md:71`) | **Confirms the record.** Migration `infra/migrations/postgres/000046_budget_reservations.up.sql`, `packages/budgetledger/ledger.go`, `services/proxy/internal/http/budget_admission.go` exist. The ledger row still carries the **pre-review** test numbers (448 passed / 94.65% / 27 integration) that the merged report corrects to 464 / 95.34% / 30 (`new findings/IBEX-1000-...:466-470`). That is a recorded claim drift, not a closure. |
| C5 | Relay daemon (`new findings/IBEX-1002-gap-011-relay-daemon-report.md:13-36`) | `packages/evidenceoutbox` was a library with no process; adds a default-off daemon, pinned least-privilege role, authoritative session fence | `GAP-011`, `GAP-005` | G4 | `provisional` (`00-status-and-evidence.md:73`) | **Confirms the record.** Default-off gate exists with validation and a config test (`services/relay/internal/config/env_config.go:41,80,161-164`, `config_test.go:14`), migration `000047_relay_fence_checker` exists, and the ledger already states fence-check/outbox/projection are not one transaction (`00-status-and-evidence.md:73`). |
| C6 | Trace inspector data contracts (`new findings/Engineering Audit_ Trace Inspector Data-Contract Gaps.md:16-25`) | No durable inference correlation ID on the context RPC; no assembly stages or payload in `ibex.llm_traces`; no transcript; no raw JSON; tool calls metadata-only | `GAP-003`, `GAP-011` | G4, G7 | GAP-003 open — registry incomplete (`18-gap-register.md:9`); operator reads are metadata-only `provisional` (`00-status-and-evidence.md:32`) | **Narrowed by contract, not fixed.** ADR-0082 (accepted 2026-09-27) deliberately exposes only `evidence_runs` metadata and states spans, candidates, prompts, completions, raw JSON and replay "remain unavailable" (`adr/0082-d2-metadata-trace-read-contract.md:20-32`). The audit's remaining gaps are therefore an accepted scope boundary, not an oversight. |
| C7 | Memory-assembly panel design (`new findings/LLM-Agent Trace Inspector_ World-Class Memory-Assembly Panel.md:3-7,259-290`) | The panel must show score contribution, rank transition, resource cost and outcome separately, from an authoritative trace | `GAP-007`, `GAP-003` | G6, G7 | GAP-007 open (`18-gap-register.md:13`); historical candidates `provisional` (`00-status-and-evidence.md:76`) | **Blocked by data, verified.** Context still scores with a labelled interim value `0.85*similarity + 0.15*confidence`, explicitly not the memory-service composite (`services/context/app/scoring.py:1-14,28-45`). No score-component, exclusion-reason or per-memory-token field reaches the wire. |
| C8 | Operator product roadmap redesign (`new findings/ibex-harness Operator Product Roadmap Redesign.md:5-22`, pinned `9b0793d6`) | Track D cannot start: no authenticated operator route, static export only, no trace/span/event identity, no durable publication, no DR | `GAP-003`, `GAP-009`, `GAP-011` | G7, G8 | Operator Console core tier `provisional`, 8 of 10 core surfaces live, platform tier `deferred` (`00-status-and-evidence.md:32-33`) | **Superseded in part.** `site/next.config.mjs` does not exist; `services/console` is a Nuxt 4 + Nitro application (`services/console/nuxt.config.ts`); 10 `core` surfaces, of which `policies` and `settings` remain `preview` (`services/console/shared/operator/surfaces.ts:107-108,143-144`). The redesign's own gate vocabulary (its G0–G6) is **not** the architecture G0–G11 and must not be aliased. |

**Net reconciliation:** of the eight clusters, three (C3, C4, C5) are implementation reports whose content is already
recorded as `provisional`; two (C1, C2) are partly stale against head; one (C6) is bounded by an accepted ADR; one
(C7) is blocked on a wire contract; one (C8) is partly superseded by ADR-0089/0090. No cluster changes a G0 accepted
decision, and none closes a gap.

## 3. Evidence status

Status vocabulary: `verified` (I read the artifact at `5a032466` and it supports the claim), `partial` (the artifact
exists but the claim's full scope is not supported), `blocked` (cannot be established without a dependency this
profile lacks), `unknown` (not checked by me). **Profile for every row unless stated otherwise:** read-only static
review of the working tree at `5a032466`. No build, lint, test, migration, container or cluster was executed for this
packet.

| # | Material claim | Status | Exact source | Profile / provenance | What was **not** run |
|---|---|---|---|---|---|
| E1 | Five G0 shapes accepted 2026-10-10; review/expiry 2026-11-10; no independent reviewer named | `verified` | `21-g0-owner-decision-record.md:3,5,7,15-24,78`; `00-status-and-evidence.md:3`; `18-gap-register.md:61` | Ledger + decision record (docs) | Nothing to run; acceptance is a dated document act. |
| E2 | Registry records 5 accepted shapes, 1 provisional lifecycle draft, 3 provisional slices, 6 `proposed` G1–G7 entries | `verified` | `03-contract-registry.md:32-38,40-70,120-186` | Docs | Nothing. |
| E3 | `policy-snapshot.v1` runtime is implemented locally and fail-closed | `partial` | `packages/policysnapshot/{snapshot,issuer,verifier,keys}.go`; `services/auth/internal/grpc/policy_snapshot.go`; `services/proxy/internal/http/policy_snapshot_middleware.go`; `00-status-and-evidence.md:77` | Source read; ledger test numbers taken at face value | Go unit suites, `-race`, integration, hosted key rotation. |
| E4 | Budget holds exist for `hard_cap` periods, with documented bounded overshoot and no extraction usage export | `partial` | Migration `000046_budget_reservations.up.sql`; `packages/budgetledger/ledger.go`; `services/proxy/internal/http/budget_admission.go`; `03-contract-registry.md:62` | Source read | Migration integration suite, worker suites, concurrency/reaper tests. |
| E5 | Relay is a deployable but default-off daemon with an explicit config-validated gate | `verified` | `services/relay/internal/config/env_config.go:41,80,161-164`; `infra/migrations/postgres/000047_relay_fence_checker.up.sql`; `00-status-and-evidence.md:73` | Source read | `go test ./services/relay/...`, real-PostgreSQL integration, ClickHouse delivery. |
| E6 | Memory create uses the shared `(org, agent, key)` PostgreSQL ledger and fails closed when it is unavailable | `partial` | `packages/ibex_idempotency/`; `infra/tests/idempotency-conformance/`; `services/memory/app/routers/memory_write_support.py:67`; `03-contract-registry.md:94`; `00-status-and-evidence.md:66` | Source read | Python and Go suites, real-PostgreSQL conformance (10 cases collected-and-skipped per the ledger). |
| E7 | Context-service callers are authenticated and tenant authority derives from the principal (ADR-0096) | `partial` | `adr/0096-context-grpc-caller-authentication.md:11,33-45`; `services/context/tests/test_grpc_auth.py`; `services/context/tests/test_principal.py`; `00-status-and-evidence.md:26` | Source read | The test files were not executed; per-user authentication, signed `PrincipalContext`, TLS and hosted evidence remain open per the ledger row. |
| E8 | Memory service initialises OpenTelemetry and redacts span content | `verified` | `services/memory/app/tracing.py`; commit `8e17a044` message (spans use `start_span` with `record_exception=False`; `hide_parameters=True`) | Source read + commit body | OTel collector round-trip, exporter-failure drill. |
| E9 | Provider credential `Get` no longer returns plaintext without a secret-scoped permission | `verified` | `services/auth/internal/grpc/provider_credentials.go:63-81` (`RequireOrgAndPermission(... permissions.SecretUse)`, `ssrf.ValidateHTTPURL`) | Source read; contrast with `5d7e0f21` where the same handler checked only org equality | Regression test for a chat-only token; proxy-consumption SSRF policy. |
| E10 | Model-policy registry no longer falls back to allow-all when Postgres is unavailable | `verified` | 0 matches for `PassthroughRegistry` at head; present at `5d7e0f21:services/proxy/internal/bootstrap/postgres.go:353` | Source read + `git show` at the audit revision | Behavioural test; what replaced it on the failure path was not traced. |
| E11 | Context budget accounts for tool schemas and formatter overhead | `verified` | `services/context/app/budget.py:3,51,73,100-102,164`; `F4-028` in commit `fa0e86ca` | Source read | Boundary tests near the model window. |
| E12 | `max_memories` truncates before canonical sort | `verified` (defect present) | `services/context/app/assemble.py:311-312`; `services/context/app/scoring.py:42-45` ("Preserves input order; the packer re-sorts … before DP") | Source read | No fix or test asserted by this packet. |
| E13 | SSE forwarding still clears the write deadline | `verified` (defect present) | `services/proxy/internal/http/stream_forward.go:86` | Source read | Slow-client soak. |
| E14 | Anthropic streaming usage is still not translated | `verified` (defect present) | No `Usage` reference in `packages/provider/anthropic/stream_translate.go` at head | Grep | End-to-end streaming usage assertion. |
| E15 | API readiness is now a live per-request check | `verified` | `services/api/app/probes.py:19-31` (`F4-020`) | Source read | Failure/recovery integration test. |
| E16 | `buf breaking` is still advisory | `verified` (open) | `.github/workflows/ci.yml:316-320` (`continue-on-error: true`) | Source read | Whether branch protection requires it (it does not, per `.github/branch-protection-main.json`). |
| E17 | No `required_evidence` database/config gate exists | `verified` | Repo-wide grep finds no such column, setting or flag outside documentation prose; `18-gap-register.md:71,84` | Grep | — |
| E18 | The audit snapshot is ~2 months behind head | `verified` | `git log --oneline 5d7e0f21..main` = 140 commits; `5d7e0f21` dated 2026-09-12; `9b0793d6` dated 2026-09-13 | Git | — |
| E19 | Console core tier is 8 live / 2 preview | `verified` | `services/console/shared/operator/surfaces.ts` (10 `core` entries; `policies` and `settings` `preview`) | Source read | Hosted two-tenant browser evidence. |
| E20 | Every audit finding **not** listed in E9–E17 | `unknown` | `new findings/*.md` referenced in §2 | Subagent-produced; **not re-run by the lead** | All of it: no suite, drill or benchmark was executed for this packet. |

### 3.1 Local-only limits (apply to every `verified` row above)

- **No hosted origin.** No environment outside the repository was exercised; the ledger records none.
- **No HA.** No replica, failover, split-brain or promotion evidence exists (`00-status-and-evidence.md:35`).
- **No restore drill.** Backup/restore is `design-intent`; no RPO/RTO has been measured (`00-status-and-evidence.md:35`;
  `15-runtime-operations-and-recovery.md:7-9`).
- **No production ClickHouse sink.** ClickHouse remains a non-production pilot, G4-gated
  (`00-status-and-evidence.md:31,73`).
- **No measured p99 SLO.** The 20 ms proxy target is ratified; the Go gate measures warm-path **means**, and no recent
  passing full-chat p99 run is published (`00-status-and-evidence.md:23,70`).
- **No integration database in this review.** Anything requiring `POSTGRES_TEST_DSN` is `partial` at best.

### 3.2 Provenance split

| Producer | Clusters | Re-run by me | Trust boundary |
|---|---|---|---|
| Lead / merged implementation reports | C3, C4, C5 | Source presence only | Numbers are the authors' recorded results (`00-status-and-evidence.md` rows), not reproduced here |
| Subagent audits pinned to `5d7e0f21` / `9b0793d6` | C1, C2, C6, C7, C8 | Spot-checked only (E9–E17) | Findings are **claims about an old revision unless restated as E9–E17** |

## 4. Material changes since 2026-10-10

Everything merged after the acceptance that touches an accepted decision or its recorded status. "Effect" is judged
against `21-g0-owner-decision-record.md`, not against the ledger's optimism.

| Change | Merge | Touches | Effect on the accepted decision |
|---|---|---|---|
| Policy snapshot runtime (issue #997, PR #998) | `745d3c28` (2026-10-17) | `principal-context.v1`, policy freshness | **Confirms** §2.1/§2.2 by implementing RS256 issuance + verification with 30 s/60 s classes; leaves key-revocation propagation and the async-continuation class unimplemented. No decision change. |
| Evidence producer + typed acknowledgement (PR #985) | `1e2b3468` (2026-10-14) | `evidence-envelope.v1` | **Narrows** the scoping gap: sanitizer and fence exist; the finalizer still runs post-response, so durable-before-ack (§2.5) is not met for chat. |
| Budget reservation ledger (#1000, PR #1001) | `f05eadb3` (2026-10-18) | `GAP-006`, budget scope | **Leaves unchanged.** §4 of the decision record explicitly does not authorise atomic budget reservation (`21-g0-owner-decision-record.md:82`); this is additive provisional work and the ledger says so (`00-status-and-evidence.md:71`). |
| Evidence relay daemon (#1002, PR #1003) | `2dbe0765` (2026-10-19) | `evidence-relay-sink.v1`, `GAP-011` | **Confirms** shape, **narrows** the "no process exists" condition. ClickHouse stays a G4-gated pilot; no production enablement. |
| Relay coverage debt (#1005) | `ec7d9334` (2026-10-19) | `GAP-011` evidence | Test-only; no decision effect. |
| Memory idempotency unification (#1006, PR #1007) | `358dfa6f` (2026-10-19) | `idempotency-operation.v1` | **Confirms** §2.3 scope for memory create, and records a **contract change**: memory moves from a Redis `(org, key)` store to the shared `(org, agent, key)` ledger (`03-contract-registry.md:94`). Legacy in-flight keys expire untouched. |
| Read-only MCP operator gateway (#1013, PR #1014) | `076f5311` (2026-10-20) | `mcp-gateway-policy.v1`, `GAP-009` | **Leaves unchanged.** MCP governance is outside the acceptance (`21-g0-owner-decision-record.md:82`); the contract text is still `proposed` (`03-contract-registry.md:158`) and the PolicySnapshot evaluator is unwired. |
| Blocking benchmark gate + p99 target ratification (#1018) | `cd5bc3b6` (2026-10-20) | `GAP-004` | **Leaves unchanged.** Target ratified; no measured p99 (`00-status-and-evidence.md:70`). |
| G0 disposition docs (#1019) | `2de742e4` (2026-10-20) | register items 4–8 | **Confirms** pending/bounded dispositions; no aliasing inferred (`18-gap-register.md:79-85`). |
| Public site rebuilt on Nuxt 4 + Docus (#1029) | `72f706b3` (2026-10-24) | citation paths | **No decision effect, but citation hygiene:** ADRs moved from `site/content/docs/adr/` to `engineering/adr/`. Audits that cite the old path now point at nothing. |
| Dashboard compatibility shell retired (#1061, ADR-0090) | `39ef0b62` (2026-11-01) | operator surface claims | **Narrows** the fleet's operator claim to one application; no G0 decision touched. |
| Security backlog triage (#1078) | `c3884caf` (2026-11-02) | container identity, fixtures | Isolation/hardening fixes (numeric UID, non-interpolated SQL fixtures). **No decision change**; confirms "no secret leakage" intent, not evidence of it. |
| ISO-MCP error text / JTI TTL (#1106) | `f3bd085f` (2026-11-03) | MCP error contract | **No decision change.** |
| Memory OTel init + redaction (#1129) | `8e17a044` (2026-11-05) | observability, `AGENTS.md` §5.1 no-secret rule | **Confirms** the redaction invariant in a newly instrumented subsystem (span status carries the exception class, not `str(exc)`). |
| Context caller authentication + principal authority (#1131, ADR-0096) | `5a032466` (2026-11-05) | `principal-context.v1`, `GAP-005` | **Narrows.** The context port is no longer unauthenticated: shared `x-ibex-context-service-token`, `hmac.compare_digest`, principal-derived directive keys, loopback-only plaintext (`adr/0096-context-grpc-caller-authentication.md:36-52`). **Not** per-user authentication, **not** a signed principal, **not** TLS. The accepted binding decision is unchanged and the ledger row is still `provisional` (`00-status-and-evidence.md:26`). |

Also relevant: `836422a5`/`1785156e`/`b460cc82` (2026-10-10 – 2026-10-14) reconciled the acceptance wording, and
`f9735c7e` registered the Round 4 G1–G7 packet. Neither moved a G0 decision.

## 5. Unresolved G0 owner decisions

Quoted or paraphrased directly from `18-gap-register.md` and the decision record. None of these is a decision this
packet can take.

| # | Item | Register / decision pointer | Why it is unresolved | Decision required | Consequence of no decision by 2026-11-10 |
|---|---|---|---|---|---|
| D1 | Named independent reviewer | `18-gap-register.md:67`; `00-status-and-evidence.md:43`; `21-g0-owner-decision-record.md:24` | The acceptance names Rick1330 acting across all roles and explicitly states no separate reviewer is named | Record a reviewer, or explicitly reaffirm that none is assigned | Every "independent review" precondition (GAP-001/002/004/006/007/011) stays unsatisfiable; the ledger cannot move past `provisional` on its own rule (`00-status-and-evidence.md:7-13`). |
| D2 | Round 5 contract-set mismatch | `18-gap-register.md:68,81` | The Round 4 packet specifies six contracts; the task brief names a different six; no aliasing was inferred | Confirm additive vs rename/combine, then update packet and registry together | The registry stays incomplete for GAP-003 while two contract vocabularies circulate; reviewers cannot tell which six are authoritative. |
| D3 | Missing packet section and fields | `18-gap-register.md:69,82` | No §4 exists in the cited packet; `memory_revision.v1` / `memory_ledger` are named but undefined | Name the authoritative source and exact contract/field names | GAP-007 stays blocked on an unnamed contract; an agent may otherwise invent a schema, which `AGENTS.md` §0 forbids. |
| D4 | `required_evidence=false` relay gate | `18-gap-register.md:71,84`; `00-status-and-evidence.md:57` | No PostgreSQL `required_evidence` column or setting exists; the relay is default-off and has no deployment approval. The daemon does construct the relay (`services/relay/internal/bootstrap/wire.go:82`), so the missing piece is the gate and the pilot auth boundary, not the caller (E17) | Identify the intended gate and pilot authentication boundary, or record that no such gate is implemented | The relay cannot be described as gated by evidence requirement; any such wording in a PR or status claim is unsupported. |
| D5 | Supported profile | `21-g0-owner-decision-record.md:7,44`; `15-runtime-operations-and-recovery.md:3`; every registry row "Profile not selected" (`03-contract-registry.md:129,139,149,169,179`) | The acceptance fixes contract defaults for a "local/protected profile" but no deployment profile is selected or certified | Select the v1 supported profile (development / single-node self-hosted / HA) and therefore the evidence gates that apply | "Profile acceptance is pending evidence" persists; no runtime row can be promoted, and G8 has no target to measure against. |
| D6 | Policy/principal trust | `21-g0-owner-decision-record.md:17-18,30-32`; `03-contract-registry.md:34,112`; `adr/0096-...md:36-52` | Caller authentication is a shared service token over an **unsigned** `PrincipalContext` on loopback; `PrincipalContextProof` is reserved but unimplemented | Accept or reject the unsigned principal for the supported profile; decide whether proof signing is required before any non-loopback deployment | The context hop cannot be described as per-user authenticated; any hosted claim would exceed evidence. |
| D7 | Budget scope | `21-g0-owner-decision-record.md:82`; `03-contract-registry.md:62`; `00-status-and-evidence.md:71` | Accepted packet excludes atomic reservation; the slice enforces only `hard_cap` and excludes finalized rows from the cap sum (bounded overshoot) | Accept the bounded-overshoot semantics and the scope (proxy admission vs extraction export) as a runtime contract | GAP-006 stays open on an unratified economic assumption; hard-cap enforcement cannot be claimed as exact. |
| D8 | Provider subset | `21-g0-owner-decision-record.md:82`; `00-status-and-evidence.md:24,55`; `18-gap-register.md:14,18` | No provider manifest/adapters are authorised; capability rows remain `proposed` with profile unselected | Name the v1 provider subset and whether the manifest is the execution authority or a hint only | GAP-008 and GAP-012 stay deferred; capability claims remain per-adapter folklore. |
| D9 | Lifecycle, retention and holds | `21-g0-owner-decision-record.md:63-65`; `03-contract-registry.md:46`; `00-status-and-evidence.md:75` | 30-day evidence baseline and legal-hold supremacy are accepted; the typed memory lifecycle is a **draft** ADR, and memory/ClickHouse retention classes are unimplemented | Accept or reject `memory-lifecycle.v1` and state the retention class per store | GAP-007 stays open; deletion completeness cannot be asserted, so no erasure claim can survive review. |
| D10 | Context fallback and session history | `new findings/Engineering Audit_ Trace Inspector Data-Contract Gaps.md:123-133,193-203`; `adr/0082-...md:20-32` | The durable conversation/raw-payload source (Postgres events vs MinIO vs dedicated store) was never chosen; ADR-0082 deliberately exposes metadata only; fallback state is not persisted (`GAP-003`) | Choose the durable conversation/raw source and whether fallback/no-assembly state is persisted | Any trace inspector beyond metadata is unimplementable without inventing a store; "why did the agent do that" stays unanswered for history. |
| D11 | Evidence acknowledgement and redaction binding | `21-g0-owner-decision-record.md:20-21`; `18-gap-register.md:35-46`; `03-contract-registry.md:196` | Durable-before-ack is accepted, but the chat finalizer runs post-response and the ack adapter is not wired to a response | Decide whether response-bound acknowledgement is required for the supported profile, or accept the post-response boundary explicitly | `evidence-envelope.v1` runtime stays `provisional`; no success path may be described as evidence-acknowledged. |
| D12 | MCP write disposition | `03-contract-registry.md:158-162`; `18-gap-register.md:15` | Read-only subset shipped locally; mutations "require approval/step-up and are not registered"; no policy-store evaluator | Confirm read-only is the entire v1 disposition, or authorise a write contract and its approval model | GAP-009 stays open; a later mutation surface would bypass an accepted boundary. |
| D13 | Recovery objectives | `00-status-and-evidence.md:35`; `15-runtime-operations-and-recovery.md:7-9`; `18-gap-register.md:17` | No RPO/RTO is measured; no restore drill exists; backups are `design-intent` | Set RPO/RTO per data class and authorise (not perform) the drill that will measure them | G8 has no acceptance threshold; the review cannot distinguish "unproven" from "unmet". |
| D14 | Provider invoice source (#859) | `engineering/console/PRE_TRACK_D_THREE_PR_REMEDIATION_PLAN.md:29`; `00-status-and-evidence.md:30` | `spent_cents_cached` is an estimate projection, not reconciled spend; `#859` remains open | Name the authoritative invoice/reconciliation source, or confirm estimate-only semantics | Cost and hard-cap claims remain estimate-grade; D7 cannot be closed either. |

## 6. W0–W9 work packages

Ordered. Every package is **documentation, contract or verification work only**. No package authorises code, schema,
dependency, configuration or deployment change; those require a separate owner acceptance and the gate named in the
last column. Roles are the repository's configured agents (`MODEL-POLICY.md` §2.1); the reviewer column is who must
sign the evidence, and no reviewer may be the author.

| ID | Objective | Owning role | Reviewer / tester | Prerequisites | Independent acceptance evidence | Gate before any code/PR |
|---|---|---|---|---|---|---|
| W0 | Resolve D1 and D5: name the reviewer and select the supported profile | `dr-rick` (owner acts) | `ibex-verifier` | This packet | Review record entry with date, reviewer, profile, and re-review date | G0 review itself; nothing downstream starts first |
| W1 | Resolve D2 and D3: reconcile the contract-set mismatch and name the missing packet fields | `ibex-architect` | `ibex-reviewer` + `ibex-verifier` | W0 | Updated packet + registry entries, or a bounded "unaddressed" record with owner signature | G0 exit wording; GAP-003 |
| W2 | Resolve D6 and D10: principal trust model and durable conversation/raw-payload source | `ibex-security` | `ibex-architect`, `ibex-verifier` | W0, W1 | ADR for each decision, citing current provenance (`adr/0096`, `adr/0082`) | G1 (trust), G7 (operator reads) |
| W3 | Resolve D4 and D11: evidence gate and acknowledgement binding | `ibex-platform-engineer` | `ibex-security`, `ibex-verifier` | W0, W2 | Decision record entry + a golden outcome table (durable / replayed / degraded / unknown) | G4 |
| W4 | Resolve D7 and D14: budget scope, overshoot semantics, invoice source | `ibex-data-engineer` | `ibex-platform-engineer`, `ibex-verifier` | W0 | Accepted contract text or explicit estimate-only statement | G3 |
| W5 | Resolve D9: accept or reject `memory-lifecycle.v1` and per-store retention classes | `ibex-memory-intelligence` | `ibex-security`, `ibex-verifier` | W0 | Owner signature on the draft ADR or a recorded rejection | G6 |
| W6 | Resolve D8 and D12: provider subset and MCP write disposition | `ibex-product` | `ibex-security`, `ibex-verifier` | W0, W1 | Manifest scope statement + MCP disposition record | G3 (provider), G7 (MCP) |
| W7 | Re-verify the audit corpus at head: reclassify every C1/C2/C6 finding as fixed / open / not-reproducible | `ibex-investigator` | `ibex-qa`, `ibex-verifier` | W0 | A dated re-audit at a pinned commit, with one command per finding | Precedes any remediation PR; prevents fixing already-fixed defects (E9, E10, E15) |
| W8 | Resolve D13: RPO/RTO per data class and the drill charter | `ibex-sre` | `ibex-platform-engineer`, `ibex-verifier` | W0, W5 | Signed objective table + drill charter (drill execution is a later gate) | G8 |
| W9 | Repair the recorded claim drift, without changing any status value | `doc-updater` | `ibex-reviewer` | W7 | Ledger row for GAP-006 carrying the merged report's numbers, or an explicit note that the older numbers stand | Documentation only; no status promotion |

Sequencing follows the table's prerequisites: W0; then W1; then W2, W4, W5 and W6, each of which depends only on W0/W1
and may run in parallel; W3 starts after W2, and W8 after W5; W7 may start once W0 is done; W9 last, after W7.
**No runtime work is authorised by this document**, and W9 must not be read as permission to re-label anything.

## 7. Claim boundary

Nothing in this packet accepts G0, promotes a status, or closes a gap.

- The five accepted G0 shapes remain `accepted` **only** for contract text and safety semantics, dated 2026-10-10
  (`21-g0-owner-decision-record.md:78`; `03-contract-registry.md:3`).
- Every runtime row named here remains `provisional`, `provisional-with-evidence`, `shipped-local` or `design-intent`
  exactly as recorded in `00-status-and-evidence.md`. This packet does not edit that file and does not restate a status
  as a different value.
- `GAP-001`–`GAP-012` statuses are unchanged. **No gap is closed by this document**, and no "partial" in §2 or §3 is a
  closure.
- The 2026-11-10 review date is unchanged. This packet is an input to that review, not a substitute for it.
- Where this packet contradicts a status claim, the controlling document wins and the contradiction is recorded here
  rather than resolved (§2 C4, §3 E12–E14). One such contradiction is already on the record: the GAP-006 ledger row
  still carries the pre-review test numbers that the merged implementation report corrects (C4).

### 7.1 If the owner does nothing by 2026-11-10

The ledger's own rule applies without further interpretation: *"When a claim expires, downgrade it to `unknown` or
`provisional` until reverified"* (`00-status-and-evidence.md:95`), and a claim is `shipped-accepted` only when the
ledger carries source commit, artifact, profile, owner/date and limitations (`00-status-and-evidence.md:7-13`).

Concretely, on 2026-11-11 and without a recorded review:

1. The **four** `accepted` rows in the ledger — `principal-context.v1`, `evidence-envelope.v1`,
   `evidence-relay-sink.v1`, `run-envelope.v1` (`00-status-and-evidence.md:64,67-69`) — pass their review date and must
   be downgraded to `unknown` or `provisional` unless the review records re-verification; they may not remain silently
   `accepted`. The fifth accepted shape, `idempotency-operation.v1`, is recorded in the contract registry
   (`03-contract-registry.md:32-38`), but its ledger entries describe runtime slices that are already
   `provisional`/`provisional-with-evidence`, so no `accepted` ledger row expires for it.
2. Every `provisional*` row whose Review column is 2026-11-10 loses its expiry cover and must be re-recorded as
   `unknown` or `provisional` with a new date and a named reverification.
3. D1 stays open, so no gap can satisfy its independent-review precondition — the `provisional` floor remains in force
   for GAP-001/002/004/006/007/011 until D1 is resolved.

Re-dating without new evidence would be a status promotion in disguise and is out of scope for any agent.

## 8. Related records

- [Decision record](21-g0-owner-decision-record.md) · [Status ledger](00-status-and-evidence.md) ·
  [Gap register](18-gap-register.md) · [Contract registry](03-contract-registry.md)
- [G0 gap audit](23-g0-gap-audit-report.md) · [Product strategy audit](20-product-strategy-gap-audit-and-recommended-redesign.md)
- [Roadmap and gates](17-roadmap-and-gates.md) · [Runtime operations](15-runtime-operations-and-recovery.md) ·
  [Failure modes](14-failure-modes-and-readiness.md)
- ADRs: [0082](../adr/0082-d2-metadata-trace-read-contract.md),
  [0083](../adr/0083-d2-publication-query-lifecycle-contract.md),
  [0084](../adr/0084-g0-principal-agent-binding-and-idempotency.md),
  [0085](../adr/0085-evidence-relay-daemon-and-session-fence.md), [0086](../adr/0086-mcp-operator-gateway.md),
  [0089](../adr/0089-product-shape-and-console-scope.md), [0090](../adr/0090-retire-dashboard-compatibility-shell.md),
  [0096](../adr/0096-context-grpc-caller-authentication.md)
