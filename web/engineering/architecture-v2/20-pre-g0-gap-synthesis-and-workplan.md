# Comprehensive Remaining Gaps Ledger

**Audit basis:** eight gap-specific source audits against clean target `main` at `7298e5ee7982b926630566c88830c99650c8eb37` (2026-10-06). Detailed notes are versioned under [`web/engineering/research/ibex-preflight-2026-10/`](../research/ibex-preflight-2026-10/README.md).

**Scope rule:** This is an acceptance ledger, not a claim that the repository is broken everywhere. A code slice is marked **verified done** only where the supplied audits show implementation and executable evidence. A merge, a proposed ADR, a local unit test, or a prior green report is not a governance acceptance artifact.

**Evidence provenance:** Eight independent research agents produced the detailed reports. The main agent verified the target checkout, clean `main` SHA, current status/contract/gap/roadmap text, issue #935 closure via PR #936, and the non-acceptance boundary. Source-path and test-level findings are attributed to the individual reports and remain subject to reviewer confirmation; this document does not claim every cited test was rerun in this session. Each report distinguishes executed tests, inspected source, external/profile evidence, and known unknowns. Owners must independently validate proposed implementation contracts before G0 acceptance.

**Current task:** The task owner expanded the earlier Development Compose-only scope to production-readiness infrastructure/setup while explicitly prohibiting deployment. Development Compose remains local-only; the production profile is unresolved. The [production infrastructure audit and no-deploy workplan](22-production-readiness-no-deploy-plan.md) records the five-area audit. Docs-only preparation is tracked by [issue #939](https://github.com/Rick1330/ibex-harness/issues/939). Issue #935 was closed by PR #936, but that closure and the merged PR do not create a dated G0 owner-approval artifact. G0 remains `UNKNOWN / NOT ACCEPTED`; this document authorizes no implementation or deployment.

## Audit-to-canonical crosswalk

The eight audit labels are research clusters, not new architecture IDs. They map to the canonical register as follows; overlaps are intentional and must not be counted as separate implementations:

| Audit cluster | Primary canonical gap(s) | Detailed evidence |
|---|---|---|
| GAP-01 identity/principal | GAP-001, GAP-002, GAP-003, GAP-005 | [Identity audit](../research/ibex-preflight-2026-10/gap-01-identity-principal-verified.md) |
| GAP-02 budget admission | GAP-002, GAP-003, GAP-006 | [Budget audit](../research/ibex-preflight-2026-10/gap-02-budget-admission-verified.md) |
| GAP-03 provider compatibility | GAP-003, GAP-004, GAP-008 | [Provider audit](../research/ibex-preflight-2026-10/gap-03-provider-compat-verified.md) |
| GAP-04 memory lifecycle | GAP-005, GAP-007, GAP-011 | [Memory audit](../research/ibex-preflight-2026-10/gap-04-memory-lifecycle-verified.md) |
| GAP-05 context compiler | GAP-004, GAP-005, GAP-007 | [Context audit](../research/ibex-preflight-2026-10/gap-05-context-compiler-verified.md) |
| GAP-06 MCP governance | GAP-003, GAP-005, GAP-009 | [MCP audit](../research/ibex-preflight-2026-10/gap-06-mcp-governance-verified.md) |
| GAP-07 evidence/recovery | GAP-003, GAP-005, GAP-011 | [Evidence/recovery audit](../research/ibex-preflight-2026-10/gap-07-evidence-recovery-verified.md) |
| GAP-08 control plane | GAP-001, GAP-002, GAP-003, GAP-005, GAP-006, GAP-009, GAP-011 | [Control-plane audit](../research/ibex-preflight-2026-10/gap-08-control-plane-verified.md) |

The 70 residual criteria below preserve every `remaining_gaps` criterion returned by those audits. The audit count is a coverage count, not a percentage-complete metric and not a substitute for canonical GAP acceptance.

## Executive decision

**G0 acceptance: UNKNOWN / NOT ACCEPTED.** No dated owner approval is recorded in `00-status-and-evidence.md` with the required exact commit, profile/dependency matrix, artifact/digests, limitations, and review/expiry date. ADR-0084 and architecture-v2 are intent/specification; PR merges are not acceptance. The eight audits consistently state that the local evidence is partial, component-scoped, or source-inspected, and that hosted/HA/recovery acceptance is absent. No governance gate is waived by this ledger.

There are **70 acceptance-level residual criteria** (the source `remaining_gaps` bullets, preserved in the coverage appendix below). None is fully closed at the acceptance level. Some have a verified code slice and are therefore **partial**; some are **blocked** by an unaccepted authority, unavailable named profile, missing runtime dependency, or external owner (#859). “Open” means implementable but not yet proven. “Blocked” means work cannot be accepted until the named external decision/profile/authority exists.

## G0 preparation stages (not G0 acceptance)

| Stage | Scope | Evidence/status |
|---|---|---|
| G0.0 — serial access and rules prerequisite | Verify the authorized repository, current base SHA, contribution/security instructions, existing tracker state, and clean topic-branch workflow before parallel review. | Completed for this docs-only preparation: clean `main` at the audit SHA, repository rules read, and docs issue #939 opened. This does not establish an execution-board owner decision or a product owner roster. |
| G0.1 — architecture/authority inventory | Read the architecture-v2 status, boundaries, contracts, security and roadmap; identify declared authorities and non-authority rules. | Completed as source audit; main-agent verification is limited to the files explicitly named in the provenance note and the canonical docs linked above. |
| G0.2 — behavior/evidence inventory | Independently map current code, tests, merged changes and evidence against each residual area. | Eight audit reports completed; see source report index. Report-level test claims still require the listed maintainers to confirm before acceptance. |
| G0.3 — profile/deployment and external-owner inventory | Identify runtime profiles, dependencies, hosted/HA evidence, privacy/finance decisions and external blockers. | Partial: Development Compose remains the local integration profile; the task owner later expanded scope to production-readiness infrastructure/setup with no deployment. The five-area audit is linked above. The Compose stack could not be executed because no runtime/daemon is available; the supported production profile, provider, dependency/artifact digests, hosted evidence, and domain-owner approvals remain unresolved. No external profile or owner approval is inferred. |
| G0.4 — sequential synthesis | Reconcile overlaps, dependencies, decision conflicts and proposed vertical work packages into one non-duplicative acceptance ledger. | Draft completed below: 70 residual criteria, shared-boundary map, explicit conflicts, W0–W9 work packages and promotion checklist. |
| Formal G0 review/acceptance | Named owners resolve choices, approve the supported profile and contract packet, and record dated evidence in `00-status-and-evidence.md`. | **Pending.** This is a separate blocking review; none of G0.0–G0.4 is a substitute for it. |

### Status legend

- **Verified done:** implementation and evidence satisfy the stated criterion at the supplied commit/profile. This status is used only for bounded slices, not for whole GAP closure.
- **Partial:** a bounded implementation/test slice exists, but a contract, cross-boundary, negative, recovery, or named-profile proof is missing.
- **Open:** no sufficient implementation/evidence for the criterion; work can proceed once prerequisites are accepted.
- **Blocked:** acceptance is prevented by a missing owner decision, unavailable required environment/authority, or an explicitly external dependency. Blocked work remains a gap.

## What is actually verified done (bounded slices only)

| Area | Verified slice | Why it is not closure |
|---|---|---|
| Identity | PR #934 (`393c8b7`) retains token-bound `AgentID`, denies selecting another agent before verifier/lookup, adds missing-verifier protected-router fail-closed behavior, and covers anti-enumeration/some inactive/missing cases. | No generated PrincipalContext, policy epoch, authenticated internal transport, run lineage, propagation, or profile acceptance. |
| Provider local substrate | Exact model-ID catalog/registry validation, startup overlays, tokenizer readiness, OpenAI/Anthropic text/stream adapters, org model policy, breakers, pre-stream error fallback; focused Go tests passed with pinned Go 1.25.13. | No immutable deployment resolver/manifest, request-time capability gate, Responses route, full fallback predicate, usage reconciliation, or named profile. |
| Memory read fences | PR #936 adds current-time predicates to vector, FTS, hydration, and hot-cache paths; historical expired inclusion is limited to dedup conflict evaluation. | No DB/profile proof, tombstone mutation, operation ledger, fan-out, observation/projection/review, or recovery certificate. |
| Context compiler | Retrieve→budget→score→pack→format, bounded DP/greedy packing, escaped nonce delimiters, gRPC assembly, Go proxy injection, 45 ms deadline, directive-only fallback. | Context RPC trusts scalar IDs; no PrincipalContext/ContextEnvelope/policy epoch, authoritative tokenizer, lifecycle gate, typed degradation, session read, or profile proof. |
| MCP | Streamable HTTP, protocol versions tested, bearer/AuthService validation, org/agent checks, three memory tools, strict input validation, dependency timeouts, Redis required/fail-closed construction in protected profiles; 185 passed/4 skipped local suite. | No canonical descriptor registry/hash, per-tool policy epoch, bounded output/deadline/cancel, durable evidence, governed writes, official conformance, or hosted/HA evidence. |
| Evidence | Atomic Postgres evidence/outbox store under RLS, uniqueness constraints, restricted relay helpers, at-least-once claim/retry/poison/stale-lease logic; focused local tests and restore-report tests. | No required-before-ack contract/runtime caller, certified/uncertified result, concrete sink/deployment, arbitrary-input redaction, tombstone fencing, non-vacuous recovery, or measured PITR/multi-store proof. |
| Control-plane substrate | Tenant/RLS directive history, request/run/tool-audit rows, operator trace metadata reads, provisional preview/dual-approval hooks, session/checkpoint storage, digest/replay hardening. | No governed skill catalog, real approval lifecycle, intent/receipt, isolated executor, composite snapshot/run manifest, rollout/rollback, or end-to-end acceptance. |

## Canonical boundaries and authority map

The following interfaces are the shared seams. They are contract boundaries, not suggestions to duplicate logic in each service.

| Boundary | Canonical authority | Required contract / non-authority rule | Current state |
|---|---|---|---|
| `AuthService/enforcement -> proxy` | Verified token claims, org, subject/agent binding, resource ownership, anti-enumeration | Callers may send selectors only; headers/body cannot override verified claims. | Agent mismatch slice partial; the common contract is open. |
| `proxy -> context/provider/worker/MCP/evidence` | Proxy/Auth-created `PrincipalContext v1` plus policy snapshot | Authenticated transport or server-bound envelope; service credentials never become end-user authority. | No common generated envelope. |
| Policy authority -> all protected work | Immutable `PolicySnapshot` `{id,digest,epoch,effective_at,expires_at}` and decision ID | Missing/stale/mismatched epoch is deny or typed 503; policy cannot be inferred from caller text. | No accepted authority/epoch propagation. |
| Principal to lineage | `RunEnvelope` / `OperationIdentity` | Run/attempt/fork IDs correlate and dedupe only; never grant authority. Resume/retry/fork revalidates principal, policy, resource, and approval. | No runtime/durable common lineage. |
| Proxy -> budget/provider | Canonical reservation ledger before provider I/O | Bound estimate, price/deployment/capability/residency facts, idempotency; no provider call after denial or reserve/outbox failure. | Cached read-only check only; no reservation state machine. |
| Memory -> context/MCP | Postgres authoritative lifecycle/active projection/tombstone | Derived vector/FTS/Redis/object/analytics stores cannot authorize or resurrect; returned hits are rechecked before ranking/use. | Read predicates partial; lifecycle authority open. |
| MCP -> memory/tools | Canonical descriptor registry + per-tool policy | Descriptor digest, tool scope, trust labels, result limits, deadlines/cancel, replay semantics. | Two schema sources; no accepted registry. |
| Canonical DB -> evidence outbox -> sink | Transactional canonical state plus stable event identity/aggregate sequence | Durable-before-ack class must be explicit; at-least-once sink dedupes; uncertified/loss is machine-visible. | Store/relay library partial; no accepted runtime/sink. |
| Evidence/memory -> deletion/recovery | Tombstone/deletion fence and certificates | Replay, restore, rebuild, and projection lag cannot resurrect deleted/held data. | No complete fence/certificate. |
| Control plane -> executor | Signed snapshot/run manifest, exact approval/intent/receipt | Host-enforced egress, brokered credentials, isolated workspace, pre-effect revalidation, quarantine and reconciliation. | Not implemented. |
| Platform/SRE -> every accepted claim | Named profile, dependency/config/image/artifact digests, measured SLO/RPO/RTO, owner/date/expiry | Local tests cannot stand in for hosted/HA/recovery evidence. | Profile evidence missing or non-vacuous. |

## Required ordering and dependency graph

1. **G0 contract and authority freeze**: owners, profiles, schemas, trust, failure, retention, redaction, replay, migration/rollback, and acceptance metadata. Do not introduce a new authority boundary before this.
2. **G1 identity/principal**: generated `PrincipalContext v1`, authenticated proxy-to-service mapping, resource scope, anti-enumeration, policy snapshot/epoch, and zero-downstream-call denial tests.
3. **G2 idempotency/replay**: canonical body hashes, tenant/key scope, collision/conflict, uncertain commit, TTL, retry/fork/attempt identity.
4. **G3 admission/provider/budget**: immutable deployment/capability/price/residency facts, atomic reservation/outbox, pre-I/O feature/token gate, provider attempt and usage semantics.
5. **G4 evidence authority**: required-before-ack classes, stable event identity, redaction, outbox/relay/sink dedupe, uncertified semantics, deletion fences.
6. **G6 memory/context**: lifecycle/observation/projection/tombstone and ContextEnvelope integration; exact-key session decision; authoritative token counting.
7. **G7/GAP-009 MCP**: descriptor/policy/limits/interop/read-only profile and then mutation governance; MCP consumes G1/G2/G4/G6, not vice versa.
8. **G8 recovery/platform**: real Postgres/ClickHouse/object/keys recovery, RPO/RTO, restore/replay/deletion proof and operational readiness.
9. **G9 control plane**: catalog, approvals, intent/receipt, isolated executor, artifacts, signed DeploymentSnapshot/RunManifest, rollout/rollback/kill switch. G9 is blocked until G0–G8 dependencies are accepted.

### Explicit conflicts and decisions required

Candidate defaults and the owner/evidence fields needed to resolve these conflicts are in the [G0 owner decision recommendations](21-g0-owner-decision-recommendations.md). They are proposals only; none is an accepted decision or implementation authorization.

- **G0 “proposed” versus “accepted”:** ADRs, architecture status, and PR merges conflict only if treated as acceptance. Resolution: status remains unknown/pending until the ledger artifact is owner-approved with evidence and expiry.
- **Token `agent_id` verified versus advisory:** repository comments and PR #934 support strict binding. Do not weaken it without an explicit product/security decision.
- **Caller IDs versus verified claims:** context, worker, MCP, and evidence currently carry different scalar subsets. Resolution: selectors remain non-authoritative; only generated/server-bound PrincipalContext is authoritative.
- **Run ID versus authority:** run/session IDs are correlation only and must not grant access. Resume/retry/fork require fresh revalidation.
- **ClickHouse/Redis/analytics versus canonical state:** they are projections/acceleration only; they cannot authorize budget, memory lifecycle, or deletion.
- **Required evidence versus fail-open async capture:** event classes must be frozen. Required-before-ack must not be silently downgraded; best-effort loss must be machine-visible and alerted.
- **G7 read-only versus current MCP writes:** hide/disable writes on read-only profiles or explicitly mark the profile provisional/local. Do not expose writes as accepted merely because handlers exist.
- **Context fallback versus security failure:** authority/integrity/policy failures deny or return typed 503; only quality/dependency degradation may use quality fallback.
- **Invoice actuals:** explicitly deferred to issue #859. Estimates must not be relabeled actuals; this is an external blocked dependency, not a local closure.
- **Session history:** decide whether exact-key checkpoint retrieval is in GAP-05. If not, record `recent_messages` as the sole history input and reject the unused `session_id` capability implication.
- **Budget scope:** current code is organization-cap only. Freeze finer resource scopes or explicitly defer them; do not imply resource-level hard caps.

## Non-duplicative remaining-work ledger

Each `W#` chunk is a planning work package, not the identically numbered architecture `G#` gate. Every chunk has one accountable owner, one independent reviewer, one tester/evidence owner, and acceptance gates. Owners are role names until the G0 roster names individuals.

### W0 — G0 governance freeze and canonical contract registry

- **Owner:** Architecture/Product Security lead.
- **Reviewer:** Architecture review board + Privacy/Legal + Finance/SRE.
- **Tester:** Release QA/evidence auditor.
- **Depends on:** none; blocks W1–W9.
- **Deliverables:** dated status-ledger row; authority/trust matrix; generated schema registry for PrincipalContext, PolicySnapshot, RunEnvelope, ContextEnvelope, Tool/Skill descriptors, OperationIntent/Receipt, EvidenceEvent, tombstone and DeploymentSnapshot; supported profiles; error/replay/idempotency/privacy/retention/hold/migration/rollback semantics; exact commit and artifact/config/dependency digests; limitations and expiry.
- **Acceptance gate:** named owner approval in `00-status-and-evidence.md`, exact commit/profile/dependencies, reproducible artifact bundle, review/expiry date, and explicit decision on every conflict above. A PR merge is not sufficient.

### W1 — PrincipalContext v1 and authenticated propagation

- **Owner:** Auth/Proxy.
- **Reviewer:** Security/Architecture.
- **Tester:** Identity integration QA.
- **Depends on:** W0.
- **Contract fields:** org, subject ID/type, auth source, agent/resource selectors, purpose/classification/residency, scopes/roles, policy snapshot ID/digest/epoch, request/trace/deadline, idempotency and operation identity, run/attempt linkage. Server-generated verified fields cannot be caller-overwritten.
- **Acceptance gate:** forged-header matrix; PAT A selecting B denied before lookup/context/provider/tool/mutation; A selecting A succeeds; missing/inactive/expired/revoked/suspended/cross-org cases; nil/outage/stale/malformed/epoch mismatch/resource mismatch typed deny/503 with zero downstream calls; cancellation/retry; exact principal/policy/request/trace/operation/run equality across one protected request. Must include named transport-auth profile.

### W2 — Canonical idempotency, operation and run lineage

- **Owner:** Platform/API.
- **Reviewer:** Data/Evidence + Auth.
- **Tester:** Distributed-systems QA.
- **Depends on:** W0 and W1.
- **Deliverables:** tenant-scoped canonical body hash, collision semantics, durable operation state, server reservation/attempt IDs, RunEnvelope, retry/fork/resume lineage, uncertain-commit reconciliation, TTL/expiry and cancellation.
- **Acceptance gate:** same key/body returns same result; changed body typed conflict; cross-tenant reuse cannot read/mutate; concurrent duplicates one authoritative effect; crash before/after commit re-drive returns existing; resume after principal/policy/resource/approval change revalidates and uses distinct attempt identity.

### W3 — Atomic budget admission and provider authorization

- **Owner:** Billing/Enforcement.
- **Reviewer:** Finance + Provider + SRE.
- **Tester:** Concurrency/chaos QA.
- **Depends on:** W0–W2; provider routing also depends on the accepted principal/policy authority from W1, and evidence coupling depends on W7.
- **Deliverables:** Postgres canonical reservation/hold/settle/release/refund/adjustment ledger and transactional outbox; conservative pre-call bound; immutable deployment/capability/tokenizer/price/residency facts; no provider call after deny/failure; ClickHouse deduplicated projection only.
- **Acceptance gate:** two replicas with one unit left never overspend; DB/outbox crashes and replay create one hold/debit/refund; unknown/stale price/tokenizer/capability, streaming/partial/cancel/timeout/retry/fallback/tool/malformed usage yield bounded typed outcomes; no provider call after denial; duplicate/out-of-order facts do not alter canonical admission; named benchmark/recovery artifact. Invoice actual reconciliation remains blocked on #859.

### W4 — Memory lifecycle, deletion and projection fencing

- **Owner:** Memory/Data.
- **Reviewer:** Privacy/Legal + Context + Evidence.
- **Tester:** DB/recovery QA.
- **Depends on:** W0–W2 and W5 identity; W7 for named recovery profile.
- **Deliverables:** typed append-only observations/projections; attribution/source taxonomy; quarantine/review; per-memory tombstone/delete/hold/expiry/supersede/merge/archive operations; durable operation state; atomic tombstone+outbox; resumable per-store fan-out, receipts/certificate and replay/version fences.
- **Acceptance gate:** cross-org/wrong-agent/deleted/held/quarantined anti-enumeration; delete-vs-vector/FTS/Redis/hydration/context race; no hit after authoritative suppression; delayed workers/restart/restore cannot resurrect; valid-time boundary at every registered path; hold blocks only required physical purge; per-memory and org deletion receipts are complete.

### W5 — Context compiler and typed ContextEnvelope

- **Owner:** Context/Memory integration.
- **Reviewer:** Auth/Privacy + Provider/Tokenizer.
- **Tester:** Context conformance QA.
- **Depends on:** W0, W1, W2, W4; tokenizer/provider authority from W3.
- **Deliverables:** authenticated proxy→context RPC; compiler-side returned-hit validation before ranking; additive versioned ContextEnvelope/Manifest with ordered typed items, source/type/trust/scope/provenance, redaction, freshness/version, policy/directive, cache/profile, omissions/degradation; authoritative final serialized-token counts and explicit stale/unknown behavior; session decision.
- **Acceptance gate:** forged/mismatched IDs and cross-tenant/deleted/expired/superseded/quarantined/malformed hits rejected; total budget includes wrappers/escaping/Unicode/tools/history/output/reasoning; security errors are deny/503, not quality fallback; exact-key checkpoint test or recorded contract decision; redacted durable manifest/recovery and 100K profile benchmark with p50/p95/p99 gate.

### W6 — MCP/GAP-009 governed read-only boundary, then mutations

- **Owner:** MCP/Security.
- **Reviewer:** Auth/Policy + Memory + Evidence.
- **Tester:** MCP interoperability QA.
- **Depends on:** W0–W5 for accepted scope; W7 for deployment evidence.
- **Deliverables:** canonical descriptor registry/hash/generated parity; per-tool policy snapshot/epoch and resource matrix; input/output/deadline/cancel/trust limits; G7 read-only profile; full-payload write/feedback idempotency and G9 approval path; official conformance and supported-client fixtures; stdio local-only policy.
- **Acceptance gate:** registry mismatch/unavailability denies; zero backend calls for forged/stale/mismatched/anti-enumeration denials; output byte and absolute deadline/cancellation tests; protected Redis readiness/fail-closed/no-op bypass tests; durable evidence before certified ack or explicit uncertified result; write disposition explicit; conformance/hosted profile artifact.

### W7 — Evidence outbox, relay/sink and recovery proof

- **Owner:** Evidence Platform/SRE.
- **Reviewer:** Security/Privacy + Data/Operations.
- **Tester:** Recovery/chaos QA.
- **Depends on:** W0–W4; consumes W5/W6 event classes.
- **Deliverables:** required-before-ack versus best-effort matrix; stable event/operation/aggregate identity; explicit certified/uncertified/unavailable response; runtime relay and least-privilege sink; redaction; tombstone fencing; metrics/alerts/drain; non-vacuous continuity/reconciliation; pgBackRest/WAL/PITR and ClickHouse/object/key restore.
- **Acceptance gate:** DB ambiguity/disabled writer/queue/relay outage cannot return certified success; same event is one sink effect across kill-after-apply; duplicate/reorder/gap/poison/restart handled; arbitrary prompt/secret/PII/error inputs redacted/rejected; all minimum classes present; nonempty restore fixture proves RPO/RTO, tenant isolation, deletion and replay fences.

### W8 — Control-plane catalog, approvals, execution and artifacts

- **Owner:** Platform Runtime/Security.
- **Reviewer:** Architecture + Security/Privacy + Release.
- **Tester:** Adversarial execution QA.
- **Depends on:** W0–W7; this is G9 and cannot be accepted earlier.
- **Deliverables:** tenant immutable skill/tool catalog; ApprovalRequest/Grant bound to exact descriptor/args/resource/policy/snapshot/expiry/approver; OperationIntent/Receipt; isolated allowlisted executor; brokered credentials, host egress/SSRF defense, workspace/artifact scan/quarantine/cleanup/reconciliation; signed DeploymentSnapshot/RunManifest; staged rollout/rollback/kill switch/key rotation.
- **Acceptance gate:** no capability self-grant; stale/foreign/forged/replayed/used/edited/revoked approval denied; fresh authenticated step-up/distinct approver; zero side effects on all denies/failures; crash before/after effect reconciles; cross-tenant/cache isolation; tamper/snapshot compatibility; restored-state verification; measurable duplicate-effect/evidence/revocation/recovery metrics.

### W9 — Named profile promotion and ledger update

- **Owner:** SRE/Release.
- **Reviewer:** Architecture governance owner.
- **Tester:** Independent acceptance auditor.
- **Depends on:** each preceding chunk’s gates.
- **Deliverables:** Compose/self-hosted/HA/hosted profile matrix, pinned image/dependency/config/artifact digests, benchmark parameters/results, recovery/RPO/RTO, alerts/runbooks, rollback, owner/date/limitations/expiry.
- **Acceptance gate:** reproducible clean-commit run; no claims from unavailable Go/pytest, local-only tests, or empty/vacuous reports; status row updated only after independent review. Promotion is per GAP, never a blanket waiver.

## Evidence deficits that must be closed

1. No formal G0/G1/G4/G8 acceptance rows with owner/date/review expiry.
2. Go tests were not executed in the identity/budget audits because `go` was absent there; Python/DB/hosted tests were also not run. The provider focused suite later passed only after sourcing pinned Go, and MCP local tests passed, but that does not repair missing profile evidence.
3. No generated common PrincipalContext/RunEnvelope/ContextEnvelope or shared transport trust mapping exists.
4. No named policy authority, policy epoch, stale/revocation window, or decision-ID artifact exists.
5. No live Postgres/RLS/pool, Redis, vector/HNSW, ClickHouse, object/artifact, logs/exports, deletion/tombstone, replay/restore matrix is proven.
6. No runtime budget reservation writer or atomic ledger/outbox path was found; `enforcement_decisions` is schema-only.
7. No canonical provider resolver/manifests/Responses endpoint/no-provider-call matrix or exact tokenizer proof.
8. Context drops lifecycle fields and uses heuristic token estimates; no typed omission/degradation contract.
9. MCP has two schema sources, async audit loss, no durable certified/uncertified semantics, no official client matrix, and uncertain cancellation/feedback authorization.
10. Evidence has no verified runtime relay/sink caller, required-before-ack response coupling, arbitrary-input redaction proof, tombstone fence, non-vacuous continuity, or measured PITR/multi-store recovery.
11. Memory source attribution is hard-coded to `user_provided`; there is no per-memory operation/certificate/fan-out/recovery proof.
12. Control-plane preview/dual-approval helpers are not real authorization; no executor, artifact quarantine, intent/receipt, signed snapshot, or rollback/kill-switch evidence.
13. External/undocumented control planes, hosted identity, customer retention policy, HA behavior, and deployment sidecars cannot be assumed as evidence.

## Residual criterion coverage register

The following preserves every supplied audit `remaining_gaps` criterion. Status is acceptance-level; the work chunk is the single non-duplicative home.

### GAP-01 — Identity/principal (8 criteria)

1. **Canonical versioned/generated PrincipalContext across HTTP/RPC/worker/MCP/provider/evidence** — **Open**, W1.
2. **Durable/runtime RunEnvelope binding run/attempt/fork/operation and fresh resume/retry validation** — **Open**, W2.
3. **Normalized subject ID/type and authentication-source taxonomy** — **Open**, W0/W1.
4. **Policy authority carrying immutable snapshot ID/digest/effective epoch downstream** — **Blocked** pending W0 authority owner, then W1.
5. **End-to-end zero-downstream-call forged/stale/missing/mismatched identity/policy/resource matrix** — **Open**, W1.
6. **Authenticated worker/MCP/evidence ingress proving service credentials are not end-user authority** — **Open**, W1/W6/W7.
7. **RLS/pool, Redis, vector, ClickHouse, object/artifact, logs/exports, deletion/tombstone, replay/restore tenant matrix** — **Open**, W4/W7.
8. **Profile-scoped owner-approved G0/G1 acceptance/recovery/benchmark/config evidence; principal seam not pending** — **Blocked** on W0/W9.

### GAP-02 / GAP-006 — Budget (7 criteria)

1. **Durable tenant-bound reservation ledger, server reservation ID, active holds, cap-aware conditional update, multi-replica serialization** — **Open**, W3.
2. **Conservative pre-call bound for context/output/reasoning/retries/fallbacks/tools/tokenizer/capability and immutable price provenance** — **Open**, W3.
3. **Budget idempotent reserve/settle/release/adjust lifecycle, collision/TTL/crash/attempt semantics, exactly-once effects** — **Open**, W2/W3.
4. **Runtime atomic `enforcement_decisions` plus canonical state/transactional outbox** — **Open**, W3/W7.
5. **ClickHouse fact uniqueness/dedup/out-of-order/lag/invalidation/restore safety** — **Open**, W3/W7.
6. **Invoice actual reconciliation (#859)** — **Blocked/external**, Finance/provider owner; estimates remain estimates.
7. **Named profile, recovery/RPO/RTO, runbook, measured contention/latency/overspend, owner/review ledger** — **Blocked** until W3 and W9 profile exist.

### GAP-03 / GAP-008 — Provider compatibility (10 criteria)

1. **Formal G0 provider contract/authority/status ledger** — **Blocked**, W0.
2. **Tenant-bound alias to immutable deployment/revision/provider/model/credential/capability-digest resolver** — **Open**, W3.
3. **Complete manifest dimensions: residency, pricing freshness, usage/retry/idempotency, safety, modalities, continuation, provenance/version** — **Open**, W0/W3.
4. **Runtime pre-provider feature/token admission, stable errors, unsupported-field semantics, denial evidence, zero calls** — **Open**, W3.
5. **Provider × feature × profile conformance fixtures** — **Open**, W3/W9.
6. **Lossless Responses route/types/fixtures** — **Open**, W3.
7. **Raw/normalized usage reconciliation and stream usage; exact tokenizer assurance** — **Open**, W3/W5.
8. **Fallback predicate combining policy/capability/budget/residency/idempotency; closed unknown and BYO/pre/mid-stream rules** — **Open**, W3.
9. **Tenant anti-enumeration/credential isolation, redacted attempt/fallback/usage evidence, manifest drift detection** — **Open**, W1/W3/W7.
10. **Named Compose/self-hosted/HA acceptance with digests/latency/usage/owner/expiry** — **Blocked** until W9.

### GAP-04 — Memory lifecycle (10 criteria)

1. **G0 lifecycle authority/contract freeze, owners/profile/retention/hold/states/migration/rollback** — **Blocked**, W0.
2. **Append-only observation/rebuildable projection with source span, actor/purpose, retention, hold, operation/model identity** — **Open**, W4.
3. **Correct extracted attribution; remove hard-coded `source='user_provided'` and set creator identity** — **Open**, W4.
4. **Quarantine review/promote/reject/correct and archive/merge/expire/delete mutation surface** — **Open**, W4.
5. **Durable per-memory operation table/API/state/cancel/status/evidence linkage** — **Open**, W2/W4.
6. **Public per-memory DELETE/tombstone with authoritative row semantics; embedding clear must not masquerade as deletion** — **Open**, W4.
7. **Per-memory cross-store fan-out/receipts/certificate/replay fence** — **Open**, W4/W7.
8. **Per-memory legal holds and physical-purge/retrieval semantics beyond org-only holds** — **Blocked** pending Privacy/Legal W0 decision, then W4.
9. **Recovery/restore/mixed-version/RPO/RTO/profile/status promotion** — **Blocked** until W7/W9.
10. **Authenticated typed ContextEnvelope and returned-hit tombstone/expiry/quarantine checks** — **Open**, W5.

### GAP-05 — Context compiler (9 criteria)

1. **Authenticated principal/purpose/resource/policy-epoch at proxy→context; forged selectors deny before work** — **Open**, W1/W5.
2. **Compiler validates every returned hit for verified tenant/agent/resource, including malformed/cross-tenant** — **Open**, W5.
3. **Lifecycle-approved projections/tombstones/quarantine/expiry/supersession/retention across every read/cache/replay/restore path** — **Open**, W4/W5.
4. **Versioned ContextEnvelope/Manifest with typed items/provenance/redaction/freshness/policy/cache/omission/degradation** — **Open**, W5.
5. **Authoritative tokenizer/model/deployment revision and final serialized count; explicit stale/unknown behavior** — **Open**, W3/W5.
6. **Failure taxonomy: authority/integrity deny/503 versus quality fallback** — **Open**, W5.
7. **Exact-key session/checkpoint retrieval or explicit recent-messages-only decision** — **Blocked** pending W0 product contract, then W5.
8. **Durable redacted manifest/degradation evidence with replay/deletion/retention/recovery** — **Open**, W5/W7.
9. **Named 100K live benchmark with p50/p95/p99 regression gate and restore/replay certificates** — **Blocked** until W5/W7/W9.

### GAP-06 / GAP-009 — MCP governance (9 criteria)

1. **Canonical descriptor authority, stable IDs/version/schema/result/digest/signature/generated parity and deny on mismatch** — **Open**, W6.
2. **Per-tool policy/resource/role/purpose/classification/epoch/decision ID and full anti-enumeration matrix** — **Open**, W1/W6.
3. **Explicit G7 read-only side-effect disposition; no unapproved write exposure** — **Open**, W6.
4. **Full-payload replay-safe idempotency, durable operation state, conflict, timeout reconciliation, feedback replay** — **Open**, W2/W6.
5. **Durable G4 evidence with IDs/redaction/ack class/crash/outage/replay/dedupe/restore** — **Open**, W6/W7.
6. **Output/content limits, absolute deadline, cancellation cleanup, untrusted result/description/PII/secret/prompt-injection handling** — **Open**, W6.
7. **Protected Redis readiness/integrity and no-op/injected bypass prevention** — **Partial**, W6 (construction/failure behavior exists; full profile proof absent).
8. **Official MCP conformance, supported clients, stdio identity/evidence policy and deployment matrix** — **Blocked** until named profiles/W9.
9. **Canonical owner/commit/profile/evidence/review status in ledger** — **Blocked**, W0/W9.

### GAP-07 — Evidence/recovery (11 criteria)

1. **Formal G0/G4/G8 owner/profile/commit/artifact/expiry acceptance** — **Blocked**, W0/W7/W9.
2. **Required-before-ack versus best-effort and explicit uncertified/unavailable loss semantics; no silent loss** — **Open**, W7.
3. **Stable event/request idempotency and lookup-existing on uncertain PersistRun commit** — **Open**, W2/W7.
4. **Named runtime relay, least privilege, concrete durable sink, drain/recovery/metrics/alerts** — **Blocked** until deployment profile, then W7.
5. **Sink dedupe by stable event/aggregate sequence/version; kill-after-apply and disorder/poison/outage tests** — **Open**, W7.
6. **Arbitrary-input redaction/privacy classification for spans/session/tools/errors/artifacts; no secret/raw prompt/PII leakage** — **Open**, W7.
7. **All minimum event classes: admission, budget, provider, context, memory/delete, MCP/tool, approval, model/artifact, operator** — **Open**, W7.
8. **Authoritative tombstone/deletion fence across replay/restore/rebuild** — **Open**, W4/W7.
9. **Non-vacuous per-aggregate continuity and canonical-vs-sink reconciliation including all outbox states** — **Open**, W7.
10. **Real pgBackRest/WAL/PITR with keys/digests/nonempty fixtures/RPO/RTO/tenant/deletion checks** — **Blocked** until infrastructure profile, W7/W9.
11. **ClickHouse/MinIO/object recovery or approved alternate policy, retention/holds/deletion receipts/replay fencing** — **Blocked** until platform policy/profile, W7/W9.

### GAP-08 — Control plane (6 criteria)

1. **G0 feature-specific registry/ADR/owners/profiles/replay/privacy/migration acceptance** — **Blocked**, W0.
2. **Tenant immutable skill/tool catalog with digest/signature/provenance/lifecycle/revocation/expiry/capability/cache isolation** — **Open**, W8.
3. **Persisted exact-action ApprovalRequest/Grant with canonical args/body/resource/policy/snapshot/expiry/approver/revocation/one-time validation** — **Open**, W8.
4. **Operation intent/receipt, governed isolated executor, host egress/SSRF, brokered credentials, artifact quarantine, cleanup, ambiguous reconciliation, zero-side-effect denials** — **Open**, W8.
5. **Signed composite DeploymentSnapshot/RunManifest, compatibility, staged rollout/abort/rollback/kill switch/replay/key rotation/restore** — **Open**, W8.
6. **Complete accepted evidence linkage for approval/tool/artifact/intent/receipt and named hosted/HA profile** — **Blocked** until W7/W8/W9.

## Promotion checklist

Before changing any canonical status from pending/provisional/open to accepted:

- [ ] The exact source commit is clean and recorded.
- [ ] G0 owner approval and all feature-specific owner/reviewer/tester names are in `00-status-and-evidence.md`.
- [ ] The profile and all dependency/config/image/artifact digests are named.
- [ ] Generated contract artifacts match runtime and schemas; mismatch/unavailable behavior is tested.
- [ ] Negative, cross-tenant, anti-enumeration, forged-selector and zero-downstream-call tests pass.
- [ ] Crash, retry, replay, duplicate, cancellation, timeout, restore, deletion/tombstone and mixed-version tests pass where applicable.
- [ ] Privacy/redaction tests show no bearer/API tokens, credentials, raw prompts, memory bodies, embeddings, or unredacted PII in evidence/logs/exports/backups.
- [ ] Named-profile latency, overspend, RPO/RTO, recovery, and operational evidence is non-vacuous and reproducible.
- [ ] Limitations and external blockers (including #859 invoice actuals) remain explicit.
- [ ] Independent reviewer signs the ledger row with a review/expiry date; no PR merge or local green test is substituted for governance.
