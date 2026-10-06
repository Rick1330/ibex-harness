# GAP-01 — Identity and Principal Verification

**Repository:** `Rick1330/ibex-harness`<br>
**Audited revision:** `main` at `7298e5ee7982b926630566c88830c99650c8eb37` (`fix(ci): align web smoke search-index limit with extract default`, PR #937 merge)<br>
**Parent chain relevant to this audit:** PR #934 merge `393c8b7d24787531e8b9c522b22b3b258c4d8cff`; PR #936 merge `125fde3da214649f319cb54e5f87b96f2ed3575c`; PR #937 merge `7298e5ee7982b926630566c88830c99650c8eb37`.<br>
**Working tree:** clean; no repository files were modified.<br>
**Scope:** GAP-01 only: principal identity, tenant/resource binding, propagation, and run envelope. Idempotency, evidence, memory, MCP, and CI changes are considered only where they affect this identity boundary.

## Disposition

**Partial.** PR #934 closed the previously visible same-organization token-bound-agent hole and added protected-profile verifier readiness checks. Those behaviors are verified in the current source and unit tests. The broader GAP-01 acceptance remains open: the repository still has no runtime, generated, versioned `PrincipalContext` or `RunEnvelope`; policy snapshot/epoch and subject/auth-source semantics are absent from the cross-boundary contracts; worker, MCP, context, provider, and evidence paths carry different scalar subsets; and no profile-scoped end-to-end acceptance artifact or formal G0 exit is recorded.

The distinction is important. The merged PRs demonstrate a **real local security hardening slice**, not completion of the architecture-v2 principal/run contract. The architecture ledger explicitly says that a merge or green local test is not an acceptance artifact (`web/engineering/architecture-v2/00-status-and-evidence.md:5-13,29-35`).

## Strategy and plan intent

The product strategy says a valid token must not be treated as access to every agent or tenant resource and that IBEX must provide hard tenant isolation and explainable policy (`IBEX Harness_ Product Strategy, Gap Audit, and Recommended Redesign.md:21-39,45-53,73-85`). The supplied GAP-01 memo narrows the work to principal identity, tenant binding/propagation, and run envelope. Its target is a verified principal derived from AuthService/enforcement, with caller identifiers remaining selectors, and a lineage-only run that never grants authority.

The canonical architecture-v2 contract is normative as a target but is still marked `specified`: every request, internal RPC, worker job, MCP call, and evidence event should carry a verified context containing organization, subject ID/type, auth source, applicable resource selectors, purpose/classification/residency, scopes/roles, policy epoch, trace/request/deadline, and mutation idempotency/operation identity (`web/engineering/architecture-v2/04-principal-policy-and-run.md:3-23`). A `RunEnvelope` must bind related attempts/context/tool/async/evidence lineage, while resume must revalidate principal, policy epoch, resource status, and approval expiry (`04-principal-policy-and-run.md:27-37`).

The implementation plan's current-state truth table already classifies this area as partial: PAT validation, org/permission extraction, and requested-agent org/status validation exist, while token-agent equality, a shared typed context/run envelope, complete propagation, and resume/retry revalidation do not (`ibex-harness-implementation-plan.md:17-29`). Its recommended sequencing puts identity/principal/run first, followed by idempotency and evidence; it does not claim that the implementation plan itself is an acceptance record (`ibex-harness-implementation-plan.md:42-53`).

## Verified local behavior

### PAT and organization claims

`packages/proto/proto/ibex/auth/v1/auth.proto:67-90` defines `ValidateTokenResponse` with `org_id`, permission bitmap, optional `agent_id`, `user_id`, `token_id`, and expiry. The proto comment now explicitly says an agent-scoped token's selected agent must equal the binding (`auth.proto:79-81`). `services/proxy/internal/auth/bearer.go` represents those values in a local `ValidateResult`.

`services/proxy/internal/http/auth_middleware.go:35-83,131-157` parses and validates the bearer, rejects missing organization context, checks any path organization match, checks required permission bits, and attaches the result to request context. The same middleware maps invalid/expired tokens to 401, suspended organizations to 403, and authentication dependency failures to 503 (`auth_middleware.go:101-127`). These are verified local HTTP behaviors, not a complete principal contract.

AuthService now retains the token-bound agent in its internal caller context. `services/auth/internal/grpc/authz.go:31-48` defines `CallerContext{OrgID, TokenID, UserID, AgentID, Permissions}`, and `authenticatePAT` copies `resp.AgentId` into it (`authz.go:83-96`). This is a meaningful fix over the older memo revision, but it is still a local AuthService context type, not `PrincipalContext`.

### Token-bound agent enforcement

The current authoritative check is `services/auth/internal/grpc/server.go:283-315` (`Server.ValidateAgent`). It first requires caller context, parses request IDs, enforces caller organization equality at lines 295-298, then rejects a non-empty caller-bound `AgentID` when it differs from the parsed requested agent at lines 299-302, before invoking `s.agentService.ValidateForOrg` at line 304. The denial is existence-safe (`codes.PermissionDenied`, generic `"forbidden"`) and is audited by `auditTokenBindDenied` (`server.go:329-335`).

The proxy repeats the check as defense in depth. `services/proxy/internal/http/agent_middleware.go:75-99` obtains the already-verified auth result, validates the requested UUID, compares `authRes.AgentID` to the parsed header UUID, and returns `403 CodeAgentNotAuthorized` before calling `h.verifier.Verify` when a bound token selects another agent. It also fails closed with a typed 503 when `h.verifier` is nil (`agent_middleware.go:47-52`). Denials are logged with requesting organization, target resource type/id, and request ID but not bearer or prompt data (`agent_middleware.go:160-171`).

The focused tests are present in the current tree:

- `services/auth/internal/grpc/validate_agent_test.go:54-76`, `TestValidateAgent_TokenBoundAgentMismatchIsDenied`, verifies same-org bound-agent A cannot request B.
- `services/proxy/internal/http/agent_middleware_test.go:92-108`, `TestUnit_AgentVerification_RejectsMismatchedBoundAgentBeforeVerifier`, verifies the proxy rejects before verifier calls (`calls == 0`).
- `agent_middleware_test.go:110-123`, `TestUnit_AgentVerification_AcceptsUppercaseBoundAgentHeader`, verifies UUID semantic comparison rather than case-sensitive header comparison.
- `agent_middleware_test.go:125-134`, `TestUnit_AgentVerification_MissingVerifierFailsClosed`, verifies a typed 503.
- `services/proxy/internal/http/router_must_test.go:81-93`, `TestUnit_NewRouter_ProtectedProfilesRequireAgentVerifier`, verifies staging and production `NewRouter` construction fails when the validator exists but `AgentVerifier` is absent.
- `validate_agent_test.go:31-52,121-171,200-227` covers organization mismatch, missing-agent anti-enumeration mapping, inactive-agent denial, and successful active-agent validation.

The source and tests verify the local acceptance slice. They do **not** prove that the same binding is carried through context RPCs, worker jobs, MCP, provider attempts, evidence, or a resumed run.

### Protected router readiness

`services/proxy/internal/http/router.go:82-107,110-124` rejects a missing agent verifier for staging/production when protected routes would otherwise be mounted. Development/test wiring remains permitted to use explicit fakes. This satisfies the proposed ADR-0084 local router requirement, but it is a construction check, not proof that every production deployment profile or alternate entry point is wired correctly.

### Existing local carriers are not one principal/run contract

The current shapes remain separate:

- `packages/proto/proto/ibex/context/v1/context.proto:21-35,96-129` carries scalar `org_id`, `agent_id`, session, request, trace, and span fields. It has no subject type, auth source, policy snapshot/digest/epoch, purpose, deadline, operation identity, or principal proof.
- `services/proxy/internal/http/chat_context_assemble.go:236-265` builds context request parameters from tenant/session/trace values already in proxy request context. This is propagation of scalars, not a server-bound `PrincipalContext`; there is no context-service authorization evidence in this path.
- `services/proxy/internal/extractionenqueue/client.go:23-37,77-127` sends `org_id`, `agent_id`, `session_id`, turns, a bearer service token, and a session-based idempotency key. `services/worker/app/tasks/extraction.py:69-109` requires the three IDs and builds a `BatchJob`; no subject/auth-source/policy epoch/run/attempt/operation envelope is present.
- `services/mcp-memory/app/principal.py:12-33` defines an independent contextvar `Principal` with org, permission bitmap, optional agent/user/token IDs. `services/mcp-memory/app/middleware.py:94-145` validates a bearer and sets that local principal. `services/mcp-memory/app/agent_verifier.py:28-70` calls `ValidateAgent` with bearer, org, and selected agent, but its interface has no token-bound-agent claim or run/policy context. MCP audit records request/org/agent/tool/outcome locally (`services/mcp-memory/app/server.py:278-321`).
- `packages/evidenceoutbox/types.go:95-122` defines `RunInput` with org/agent/session/request/trace/span/checkpoint/turn and evidence details. `services/proxy/internal/http/session/evidence.go:73-118` maps a completed post-response snapshot into it. There is no subject type/auth source/policy snapshot/epoch/attempt/operation identity or authorization proof. Evidence persistence is also optional and fail-open at the call site (`evidence.go:16-64`).
- `services/proxy/internal/http/session/types.go:28-40,62-112` has `Resolved` session identity and `SnapshotMeta` fields. These are useful local correlation/checkpoint types, not a logical run authority or durable `RunEnvelope`.

A bounded repository search at this revision found no runtime or generated implementation of `PrincipalContext`, `RunEnvelope`, `principal-context.v1`, or `run-envelope.v1`. `web/engineering/architecture-v2/03-contract-registry.md:33-57` labels `principal-context.v1` proposed and `run-envelope.v1` specified/not implemented; its rows explicitly say cross-boundary evidence and the contract matrix are pending.

## Acceptance-criterion audit

The following criteria are the GAP-01 memo's required tests/benchmarks (`gap-01-identity-principal.md:92-102`) interpreted against the current `main`. “Resolved” means the bounded behavior is implemented and directly covered locally; it does not mean `shipped-accepted` unless the ledger evidence rule is also satisfied.

| Criterion | Classification | Verified current evidence and merged-PR evidence | Residual qualification |
|---|---|---|---|
| (a) PAT user/agent/service/operator identity map, including missing/stale/expired/revoked/org-suspended cases | **Partial** | PAT org/permission/optional agent/user/token/expiry fields are in `auth.proto:72-90`; proxy auth rejection is in `auth_middleware.go:57-81,101-127`; `CallerContext` carries PAT fields in `authz.go:31-38,83-96`; related auth tests cover invalid/expired and suspended paths. PR #934 (`393c8b7`) added the `AgentID` caller propagation. | There is no normalized subject ID/type, auth source, purpose, scopes/roles, policy epoch, deadline, or cross-plane identity map. Operator sessions and MCP use separate local models. Service credentials are not represented as an end-user principal. No profile-level revocation/staleness evidence is recorded. |
| (b) Token-bound agent A requesting same-org B is denied; matching binding succeeds; cross-org/missing/inactive cases remain anti-enumeration-safe | **Resolved for the AuthService/proxy slice; partial for GAP-01 overall** | AuthService denies bound mismatch before `ValidateForOrg` (`server.go:295-304`); proxy denies before verifier (`agent_middleware.go:88-98`); tests named above prove mismatch, match, uppercase UUID, cross-org, missing, and inactive mappings. PR #934 changed `authz.go`, `server.go`, `auth.proto`, `agent_middleware.go`, and both test files; its merge commit is `393c8b7d...`. | No cross-boundary integration test proves the same decision for context/provider/worker/MCP/evidence. The proposed G0 packet is still pending. |
| (c) Nil verifier and auth/policy dependency failures deny and assert zero context/provider/tool calls | **Partial** | Nil verifier returns 503 in `agent_middleware.go:47-52`; protected staging/production router construction rejects it in `router.go:82-124`; tests are `TestUnit_AgentVerification_MissingVerifierFailsClosed` and `TestUnit_NewRouter_ProtectedProfilesRequireAgentVerifier`. Auth dependency failures map to 503 in `auth_middleware.go:120-127`; agent verifier timeout/unavailability maps to `ErrAgentVerifyUnavailable` in `services/proxy/internal/auth/agent_verifier.go:68-109`. | No test spans the full chain and asserts zero context/provider/tool calls for every auth/policy failure. There is no runtime policy-snapshot authority or stale-policy check, so the policy half of the criterion is open. |
| (d) Forged org/agent headers cannot override verified claims | **Partial** | Proxy organization authorization uses the validated `ValidateResult.OrgID` and optional path match (`auth_middleware.go:131-143`); agent selection is compared to verified token-bound `AgentID` (`agent_middleware.go:88-97`) and AuthService checks caller org (`server.go:295-302`). | Context, worker, MCP, evidence, and management surfaces still accept scalar IDs in boundary-specific contracts. There is no canonical verified-vs-selector field distinction or mixed-boundary forged-header matrix. |
| (e) Connection-pool RLS reset and org-switch isolation | **Open for GAP-01 acceptance** | PR #936 (`125fde3`) hardened memory validity predicates and related local memory tests; it did not add a principal/transport or connection-pool identity contract. The architecture gate explicitly requires RLS/connection-pool tests (`13-security-invariants-and-test-gates.md:16-18`). | No repository evidence was found for a GAP-01 end-to-end org-switch/pool-reset matrix across all authoritative stores. Memory-local isolation is not proof of principal propagation or complete tenant isolation. |
| (f) Context/MCP/worker/evidence propagation equality plus replay/resume revalidation and mismatch rejection | **Open** | Current carriers are the scalar context proto (`context.proto:21-35`), extraction request/task (`extractionenqueue/client.go:30-37`; `extraction.py:79-104`), MCP `Principal` (`principal.py:12-33`), and evidence `RunInput` (`types.go:95-122`). | No `PrincipalContext` or `RunEnvelope` implementation exists. No policy epoch, subject type/auth source, attempt/fork identity, or resume revalidation is present. This is the central unresolved GAP-01 boundary. |
| (g) Store-specific cross-tenant existence/cache/vector/analytics/object/log/export/deletion tests | **Partial** | Existing memory isolation tests in `services/memory/tests/integration/security/test_memory_iso_1_isolation.py` cover cross-org search/agent denial, malformed RLS floor, relationship insert, HNSW, and hot-cache cases. PR #936 added temporal validity fences in memory read paths and focused tests; the gap register calls these partial hardening. | The required matrix spans Postgres/RLS, Redis, vector, ClickHouse, object/artifact, logs/exports, and deletion/replay. The current evidence is subsystem-specific and does not prove a shared principal or complete SEC-001 invariant. |
| (h) Deadline/cancellation and idempotent retry/crash/replay | **Partial** | Agent verification has a bounded timeout (`agent_verifier.go:49-57,68-81`). PR #934 added tenant-scoped idempotency validation and replay hardening in `packages/idempotency/*` and proxy chat idempotency files; its commit stat explicitly records those files. PR #936 added local evidence digest/ack-loss replay hardening. | These are separate local mechanisms. A run does not bind retry attempts or force fresh principal/policy/resource/approval validation; no shared operation/run identity crosses all boundaries. |
| (i) Secret/privacy checks on logs/evidence | **Partial** | Agent denial logging uses IDs/outcomes without the bearer (`agent_middleware.go:160-171`); MCP audit emits org/agent/tool/outcome fields (`server.py:310-320`); evidence/tool types use sanitized audit fields (`types.go:64-72`). PR #934 hardened malformed evidence rows; PR #936 added payload digest validation and replay tests. | No complete GAP-01 cross-plane redaction test proves that raw tokens, prompts, memory bodies, embeddings, or PII cannot enter every log/evidence path. ADR-0084's privacy language is proposed, not accepted (`0084-g0-principal-agent-binding-and-idempotency.mdx:79-87,123-135`). |
| (j) Profile-scoped integration/recovery artifact and benchmark/config digest for any latency/SLO claim | **Open** | The status ledger requires source commit, evidence artifact, profile/dependencies, owner/date, limitations, and review date (`00-status-and-evidence.md:5-13`). PR #934's local/hosted checks and PR #936's local PostgreSQL relay/memory tests are component evidence only. PR #937 changes CI search-index limits only and has no GAP-01 functional evidence. | No dated owner decision, named supported profile, cross-boundary artifact, recovery drill, or accepted benchmark/config digest for principal/run propagation exists. |

## Merged PR assessment

### PR #934 — merged as `393c8b7d24787531e8b9c522b22b3b258c4d8cff`

**Verified contribution:** This is the relevant GAP-01 implementation slice. Its merged file list includes `auth.proto`, `services/auth/internal/grpc/authz.go`, `server.go`, `validate_agent_test.go`, proxy `agent_middleware.go` and tests, `router.go`, and `router_must_test.go` (commit stat `393c8b7.stat.txt:61-99`). The current code confirms the intended claims: token-bound `AgentID` is propagated into `CallerContext`; AuthService denies mismatch before agent lookup; proxy denies before verifier; protected staging/production routers reject absent verifiers; uppercase UUIDs are handled semantically. The added tests directly support those claims.

**What it did not do:** It did not add the canonical principal/run schema, policy snapshot/epoch, subject type/auth source, worker/MCP/context/evidence propagation, run resume revalidation, or profile acceptance. The session report itself says the broader G0–G8 gates were not finished and lists formal G0 acceptance, typed context, memory/context, MCP, and recovery as future work (`SESSION_REPORT_2026-10-06.md:410-473`).

### PR #936 — merged as `125fde3da214649f319cb54e5f87b96f2ed3575c`

**Verified contribution:** PR #936's file list is dominated by memory validity predicates, MCP protected-profile Redis limits, evidence relay digest/replay changes, focused tests, and architecture/G0 documentation. Its current architecture documents still say the G0 packet is proposed and that `principal-context.v1` is proposed while `run-envelope.v1` is not implemented (`00-status-and-evidence.md:29-35`; `03-contract-registry.md:29-57`).

**GAP-01 effect:** It strengthens adjacent fail-closed/tenant safety but does not implement the shared principal or run envelope. Its MCP verifier still receives only bearer/org/agent (`agent_verifier.py:28-70`), and the MCP `Principal` remains a separate local dataclass. The gap register keeps the principal seam as “bounded post-G0 slice only” and says GAP-005/GAP-011 remain non-accepted (`18-gap-register.md:22-30,34-45`).

### PR #937 — merged as `7298e5ee7982b926630566c88830c99650c8eb37`

PR #937 changes `.github/scripts/check-search-index-limit-sync.sh`, web smoke/deploy workflows, and CI configuration only. It has no identity, authorization, propagation, run, or evidence-contract changes. It is nevertheless the requested clean-main tip and was included to ensure the audit is against the exact current revision.

## Residual subgaps and risks

1. **No canonical principal implementation.** AuthService's response, proxy `ValidateResult`, context protobuf, worker payload, MCP `Principal`, and evidence `RunInput` overlap but are not one versioned security contract. A future implementation must distinguish verified authority from caller selectors and prevent overwrite.
2. **No canonical run envelope.** Session/checkpoint/evidence run IDs exist independently. There is no server-minted run/attempt/fork/operation model that binds context, provider attempts, tools, async work, approvals, and evidence while revalidating on resume.
3. **Policy authority is missing from runtime identity.** No policy snapshot ID/digest or effective epoch is present in the inspected context, worker, MCP, or evidence shapes. Missing/stale/contradictory policy therefore has no shared enforcement point.
4. **Identity taxonomy is incomplete.** There is no normalized subject type/auth source distinction for user PAT, agent PAT, service caller, operator session, or delegated identity. Permission bits alone are not a complete resource authorization decision.
5. **Propagation trust is unproved.** Context and worker boundaries are scalar and MCP uses a separate local principal. The worker service token must not be promoted to end-user authority, and each ingress needs authenticated mapping and revalidation.
6. **End-to-end zero-downstream-call evidence is absent.** The local proxy test proves verifier call count zero for one mismatch, but there is no test asserting no context/provider/tool/mutation invocation across all paths for forged, stale, missing, or mismatched identity.
7. **Tenant evidence is incomplete across stores and lifecycle.** Memory-specific tests and PR #936 fences do not prove Redis, ClickHouse, object/artifact, logs/exports, deletion, restore, or connection-pool reset isolation.
8. **Protected readiness is profile-limited.** `NewRouter` gates staging/production, while test/development exceptions are permitted. Alternate deployment/entrypoint wiring and all protected service boundaries still require profile evidence.
9. **Acceptance/governance remains open.** G0 is explicitly pending owner review; GAP-001–003 and the GAP-005 principal seam remain non-accepted. A merged PR or passing component test must not be promoted to `shipped-accepted`.
10. **Revocation/staleness and availability semantics are profile-dependent.** Local auth/cache and bounded timeouts exist, but no universal stale-claim SLA or deployed-profile recovery evidence was found in this audit.

## Dependencies and shared boundary ownership

The architecture-v2 boundary matrix (`04-principal-policy-and-run.md:39-49`) and registry (`03-contract-registry.md:59-67`) imply the following ownership that must be frozen before acceptance:

- **AuthService/enforcement plane:** authoritative token validation, organization, subject, token-bound agent, resource ownership, permission/scope decision, and anti-enumeration errors. This includes the current AuthService/proxy hardening.
- **Policy authority:** named owner for immutable policy snapshot ID/digest and effective epoch, freshness, expiry, and stale/missing behavior. No such runtime authority was verified here.
- **Proxy/Auth:** HTTP admission, server-bound principal mapping, protected-router readiness, request/trace/deadline and operation identity; caller headers remain selectors.
- **Context owner:** authenticated proxy-to-context `PrincipalContext v1` mapping and rejection of forged/mismatched selectors before retrieval/ranking/packing.
- **Worker/extraction owner:** authenticated operation/run ingress, tenant/resource/policy revalidation before mutation, retry/attempt identity, and no use of worker service credentials as end-user authority.
- **MCP/Security:** resource-server principal, tool registry/policy scope, token-bound agent semantics, rate/dependency failure, and audit mapping. PR #936's protected Redis limiter is adjacent hardening, not this contract.
- **Evidence/Platform:** server-generated event/run envelope, redaction, stable event/aggregate/operation identity, PostgreSQL authority, relay/sink dedupe, and explicit acknowledgement/uncertified behavior.
- **PostgreSQL/RLS and lifecycle owners:** connection-pool reset, tenant predicates, deletion/tombstone fencing, cache/vector/analytics/artifact projections, replay and restore behavior.
- **Deployment/SRE:** named supported profile, transport authentication between services, dependency inventory, hosted/HA evidence, recovery artifacts, and review/expiry dates.

Graph/A2A/marketplace/sandbox and broad provider expansion are explicitly deferred and are not dependencies for GAP-01 (`00-status-and-evidence.md:19-27`; `17-roadmap-and-gates.md:17-18`).

## Exact acceptance checks before GAP-01 can be promoted

1. **G0 record:** Add a dated status-ledger acceptance record naming Auth/Policy, Contract, Evidence/Security, and Deployment owners; exact source commit; selected profile/dependencies; evidence artifact; limitations; and review/expiry date. Resolve required/optional fields and trust labels before new cross-boundary implementation.
2. **PrincipalContext v1:** Add an additive, generated, versioned contract carrying required org, subject ID/type, auth source, applicable selectors, purpose/classification/residency, scopes/roles, policy snapshot ID/digest/epoch, trace/request/deadline, and mutation idempotency/operation identity. Make verified fields server-bound and selectors non-authoritative.
3. **Token binding matrix:** Test agent-scoped PAT A selecting same-org B: existence-safe denial before AuthService agent lookup and before context/provider/tool/mutation calls; test A selecting A succeeds; test org-scoped tokens selecting active agents; test cross-org, missing, inactive, expired, revoked, and suspended cases with stable anti-enumeration responses.
4. **Fail-closed dependency matrix:** Test nil verifier, auth outage, policy outage, malformed/stale context, missing policy epoch, and resource-status mismatch. Assert typed 503/deny and zero downstream calls. Include deadlines, cancellation, timeout, and retry behavior.
5. **Header/selector forgery:** Send forged org, agent, project, session, run, and resource headers at every ingress. Assert they cannot overwrite verified principal fields or widen scope; test mixed-version/additive compatibility where applicable.
6. **Context/worker/MCP/evidence equality:** Execute one protected request through context assembly, provider attempt, extraction/MCP path, and minimum evidence record. Assert principal org/subject/type/agent, policy snapshot/epoch, request/trace, operation, and run/attempt linkage match at each boundary; reject missing/mismatched/stale envelopes.
7. **Run revalidation:** Resume/retry/fork a run after changing principal status, policy epoch, resource status, or approval expiry. Assert fresh revalidation and denial; assert distinct attempt identity and no duplicate authoritative effect.
8. **Tenant/store matrix:** Exercise PostgreSQL/RLS with connection-pool org switching, Redis keys/cache, vector/HNSW, ClickHouse analytics, object/artifact, logs/exports, deletion/tombstones, replay, and restore. Include existence-safe misses and stale/tombstoned replay negatives.
9. **Privacy evidence:** Assert bearer/API tokens, credentials, raw prompts, memory bodies, embeddings, and unredacted PII never reach ordinary logs/evidence. Record redaction class and deterministic references where allowed.
10. **Profile evidence:** Run the matrix on the named supported deployment profile, record dependency/config/image digests, recovery/restore artifact, and any benchmark/SLO workload. Do not claim hosted/HA acceptance from local unit tests.

## Uncertainties and falsifiers

- The current tree verifies the intended strict meaning of token `agent_id` in the proto and code. If product owners intend it to be advisory, that would contradict `auth.proto:79-81` and ADR-0084 and requires a new decision; until then strict binding is the safe interpretation.
- This audit did not execute Go tests because the sandbox has no `go` executable. Test definitions and source were inspected. No claim is made that the current test suite passed in this environment. Python/DB integration and hosted profile tests were likewise not run.
- No external deployment/control-plane mechanism was assumed. An external mechanism could change the deployment conclusion only if it is named, authenticated, included in the supported profile, and linked from the status ledger with artifacts.
- The absence of `PrincipalContext`/`RunEnvelope` symbols is bounded to the inspected repository at commit `7298e5e`; it does not rule out undocumented external middleware. Undocumented controls cannot satisfy the repository acceptance rule.

## Source references

- Assigned gap memo: `/home/ubuntu/ibex-harness-workspace/preflight/ibex-preflight docs/gap-01-identity-principal.md`
- Product strategy: `/home/ubuntu/ibex-harness-workspace/preflight/ibex-preflight docs/IBEX Harness_ Product Strategy, Gap Audit, and Recommended Redesign.md`
- Implementation plan: `/home/ubuntu/ibex-harness-workspace/preflight/ibex-preflight docs/ibex-harness-implementation-plan.md`
- Session report: `/home/ubuntu/ibex-harness-workspace/preflight/ibex-preflight docs/SESSION_REPORT_2026-10-06.md`
- Canonical requirements: `web/engineering/architecture-v2/00-status-and-evidence.md`, `03-contract-registry.md`, `04-principal-policy-and-run.md`, `13-security-invariants-and-test-gates.md`, `17-roadmap-and-gates.md`, `18-gap-register.md`
- Proposed G0 ADR: `web/content/docs/adr/0084-g0-principal-agent-binding-and-idempotency.mdx`
- Merged PR evidence: `393c8b7d24787531e8b9c522b22b3b258c4d8cff` (#934), `125fde3da214649f319cb54e5f87b96f2ed3575c` (#936), `7298e5ee7982b926630566c88830c99650c8eb37` (#937)
