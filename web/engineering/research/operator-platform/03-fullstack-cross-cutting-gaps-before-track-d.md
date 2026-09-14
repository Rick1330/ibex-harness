# Full-Stack Engineering Audit: Cross-Cutting Gaps Before Phase 4 Track D

**Repository:** `Rick1330/ibex-harness`  
**Audited revision:** `5d7e0f21af402b551351e6272da7f5464e106d1b`  
**Scope:** Seven independent engineering angles affecting Track D readiness. The prior trace-inspector findings are not repeated unless new evidence materially changes their severity or scope.

## Executive disposition

The highest-risk new findings are in authorization and operational safety. The Auth provider-credential Get RPC returns decrypted provider secrets without checking the `OrgSettingsWrite` permission, and the proxy forwards the end-user bearer token to that RPC. BYO-provider destination validation is also enforced only in one API orchestration path, not at the Auth write boundary or proxy consumer, leaving an SSRF and DNS-rebinding/TOCTOU gap. API readiness is checked only at startup, so the service can remain ready after Auth or Postgres becomes unavailable.

The main correctness risks are concentrated in context budgeting and memory ranking. Tool schemas and formatter overhead are excluded from the budget calculation; configured memory rank weights are validated but ignored; multi-label memories decay using only their primary category; and the bucketed packer can return a lower-value memory set after lossy repair. Additional contract gaps include silently discarded context RPC fields, unimplemented advertised RPCs, Anthropic streaming usage loss, and a non-enforced Buf breaking-change check.

### Classification legend

- **P0:** Tenant-isolation or security break.
- **P1:** Production correctness or security defect affecting behavior.
- **P2:** Missing hardening or deferred capability that can become a release risk.
- **P3:** Documentation drift only.

Each finding is classified as **undocumented-but-real bug**, **documented-but-unimplemented**, **implemented-but-unreachable-by-consumer**, or **docs-stale**.

## 1. AuthN/AuthZ, tenancy, and secrets

### 1.1 Provider credential Get returns plaintext without `OrgSettingsWrite`

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; **blocks an authenticated dashboard or provider-management rollout**.

`services/auth/internal/grpc/provider_credentials.go:58-83` authenticates the caller and checks only organization equality. Unlike Create at `:32-34`, Delete at `:93-95`, and List at `:112-114`, it never calls `RequireOrgAndPermission`. `services/proxy/internal/credentials/resolver.go:162-170` forwards the end-user bearer token to `GetProviderCredential`, and `services/auth/internal/grpc/provider_credentials.go:79-82` returns decrypted `ApiKey` and `BaseUrl`. `packages/permissions/permissions.go:32` defines `OrgSettingsWrite` separately from `ProxyChatCompletion` at `:49-50`.

Any authenticated same-organization principal that can reach the Auth gRPC service can therefore retrieve the organization’s plaintext provider key, even when its token is intended only for proxy chat. Require a narrowly scoped internal service capability for secret retrieval, prevent ordinary chat principals from receiving `ApiKey` or `BaseUrl`, and add a regression test for a token containing `ProxyChatCompletion` but not `OrgSettingsWrite`.

**Change type:** Authorization logic change; no database migration required. Secret exposure requires immediate remediation and rotation policy review.

### 1.2 BYO provider BaseURL validation is bypassable at the Auth/proxy boundary

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; **blocks tenant-facing BYO-provider configuration and any dashboard action that invokes it**.

The normal API path validates the destination at `services/api/app/services/providers.py:100-104`, but the Auth gRPC boundary accepts `req.GetBaseUrl` directly at `services/auth/internal/grpc/provider_credentials.go:29-41`. The service persists the trimmed value without scheme, host, DNS, redirect, or private-address validation at `services/auth/internal/service/provider_credentials.go:127-135`. The proxy copies it into `Request.BaseURLOverride` at `services/proxy/internal/http/chat_provider.go:137-148`, and the OpenAI-compatible and Anthropic clients use it to construct outbound URLs at `packages/provider/openaicompatible/client.go:78-83` and `packages/provider/anthropic/client.go:78-83`.

The validation probe pins a resolved public IP only for that transient probe (`services/api/app/services/provider_validate_net.py:31-41`), while the proxy later resolves the stored hostname again. A direct Auth caller can persist an attacker-controlled destination, and even the guarded API path has a DNS-rebinding/TOCTOU concern unless later connections reuse the validated policy. Validate and canonicalize at the Auth write boundary, enforce the same policy at proxy use, reject loopback/private/link-local/reserved destinations unless explicitly allowed, disable redirects, and test DNS rebinding.

**Change type:** Validation and outbound-HTTP policy change; likely no schema migration, but persisted invalid rows require read-time defense in depth.

### 1.3 MFA-gated directive operations have no enforcement path

**Severity:** **P2**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Open; follow-up unless Track D exposes directive promotion or revocation.

`packages/permissions/permissions.go:16-17` labels `DirectivePromote` and `DirectiveRevoke` as MFA-required, but `:77-80` only tests bitmap membership. `services/api/app/authz.py:51-70` implements role and bitmap checks without MFA input, challenge verification, or freshness validation. The API documentation promises `X-MFA-Code` at `web/engineering/API_DOCUMENTATION.md:1634-1647` and `:1694-1697`, while `4.d.4` remains planned and lists MFA re-entry as unchecked at `web/content/roadmap/phase-4-multi-provider/milestones/4.d.4-drift-alerts-directive-management.mdx:1-5,81-83`.

Implement a user- and operation-bound MFA challenge with replay/freshness protection, or narrow the published contract until enforcement exists.

**Change type:** New authorization workflow; no pure additive permission-bit change is sufficient.

## 2. Proxy hot path

### 2.1 Canceled idempotent requests leave a pending claim until TTL expiry

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; follow-up for general Track D, but blocks reliable retry behavior.

`services/proxy/internal/http/chat_provider.go:55-66` claims the idempotency key before dispatch. It returns on pre-dispatch cancellation at `:68-80` and on provider `context.Canceled` at `:90-102` without calling Finish or Release. The release paths are in `services/proxy/internal/http/chat/idempotency.go:253-283`, while `packages/idempotency/store.go:93-112` gives pending claims a nine-minute TTL.

A client disconnect or deadline can therefore cause a legitimate retry to receive `IDEMPOTENCY_IN_PROGRESS`/409 for up to nine minutes. Install cancellation cleanup with ownership-safe CAS semantics and add tests for cancellation before dispatch and provider cancellation.

**Change type:** Go control-flow fix and tests; no schema migration.

### 2.2 Idempotency replay mutates session state before replay detection

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; blocks flows whose dashboard behavior relies on sticky-session turn metadata.

`services/proxy/internal/http/chat_provider.go:55-63` resolves the session before resolving idempotency. `services/proxy/internal/http/chat_session_bridge.go:28-57` performs session lookup/creation, and `services/proxy/internal/http/session/lifecycle.go:33-39,53-78` can increment or populate session turn state before the replay short-circuit. This conflicts with the replay contract in `web/content/docs/adr/0035-chat-idempotency-key.mdx:23-30`, which promises no provider call, checkpoint, or trace enqueue.

Resolve or claim idempotency before session lifecycle work, or make replay bypass all session mutation. Add a duplicate-key test that asserts no session lookup/creation and no `TurnCount` change.

**Change type:** Go ordering/side-effect fix; no migration.

### 2.3 Monthly token quota is advertised but absent

**Severity:** **P2**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Deferred as issue `#806`; blocks cost-governance claims if exposed in Track D.

`web/engineering/API_DOCUMENTATION.md:208-211` documents a 429 `QUOTA_EXCEEDED` monthly-token contract. The proxy configuration at `services/proxy/internal/config/config.go:60-65` and limiter at `packages/ratelimit/hierarchical.go:76-83,128-150,224-239` implement only per-minute RPM keys. The roadmap explicitly defers `month_tokens` to issue `#806` at `web/content/roadmap/phase-4-multi-provider/milestones/4.b.1-lua-hierarchical-rate-limiter.mdx:26-35,53-59`.

Implement atomic provider-usage debit and failure/stream completion policy, or remove/narrow the generic monthly-quota promise.

**Change type:** New rate-limit accounting and likely Redis/schema/API changes.

## 3. gRPC and proto contract integrity

### 3.1 Buf breaking-change detection is informational, not a merge gate

**Severity:** **P2**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Open; follow-up before expanding v1 contracts.

ADR 0004 requires `buf breaking` at `web/content/docs/adr/0004-protobuf-and-codegen-policy.mdx:24-31`. However, `.github/workflows/ci.yml:283-310` sets `continue-on-error: true`, `:2383-2388` does not include the job among gate dependencies, and `.github/branch-protection-main.json:1-11` does not require `buf-breaking`.

A field-number, field-type, or removed-RPC change can therefore pass required CI while breaking existing consumers. Make the check failure-propagating and required, or explicitly revise the compatibility policy.

**Change type:** CI and branch-protection configuration; no runtime migration.

### 3.2 Context v1 budget and ranking controls are silently discarded

**Severity:** **P2**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Open; blocks any dashboard control that exposes these options.

The wire contract declares `available_tokens` and four score weights at `packages/proto/proto/ibex/context/v1/context.proto:21-40`. `services/context/app/server.py:349-374` omits `available_tokens`, and `:392-405` maps only `skip_cold_memories`, `skip_hot_memories`, and `max_memories`; the four score weights are ignored. `packages/contextclient/types.go:16-26` confirms the omitted fields remain deferred.

A caller can send a syntactically valid request and receive a successful response computed with server defaults. Implement the fields end to end, reject unsupported values explicitly, or version the contract so callers cannot mistake ignored inputs for applied controls.

**Change type:** Additive proto/client/server implementation or explicit contract versioning.

### 3.3 Two advertised ContextAssemblyService RPCs always return `UNIMPLEMENTED`

**Severity:** **P2**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Open; blocks Track D only if it exposes context search or feedback.

The service exposes `AssembleContext`, `SearchMemories`, and `RecordMemoryFeedback` at `packages/proto/proto/ibex/context/v1/context.proto:7-19`. `services/context/app/server.py:92-104,129-137` stubs the latter two with `UNIMPLEMENTED`, and ADR 0038 documents the deferral at `web/content/docs/adr/0038-context-assembly-service.mdx:21-32`.

Keep these methods out of a shipped capability surface until implemented, or add capability negotiation and a versioned partial-service contract.

**Change type:** Implementations are additive; removing or changing advertised behavior may require versioning.

### 3.4 Proto-generation guidance is stale relative to CI

**Severity:** **P3**  
**Classification:** **Docs-stale**  
**Status:** Open; documentation follow-up only.

`packages/proto/buf.gen.yaml:1-3` and ADR 0004 at `:33-37` say generation is not run in CI, but `.github/workflows/ci.yml:312-335` runs ephemeral `buf generate`. `packages/proto/README.md:46-55` describes the CI behavior correctly.

Reconcile the comments and ADR with the actual ephemeral-generation policy.

**Change type:** Documentation only.

## 4. Multi-provider and model routing

### 4.1 Anthropic streaming drops usage metadata

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; blocks correct Anthropic streaming usage and cost analytics.

`packages/provider/anthropic/retry.go:59-72` wraps every streaming response in the translator without setting `Usage`. `packages/provider/anthropic/stream_translate.go:240-320` does not translate `input_tokens` or `output_tokens`, and `:409-426` emits translated chunks without a usage object. The proxy obtains stream usage at `services/proxy/internal/http/stream_forward.go:64-80,207-216`, while `packages/provider/openaicompatible/stream_accumulator.go:120-131` populates usage only when a usage-bearing chunk exists.

Successful Anthropic streaming requests can therefore record zero or nil usage in checkpoints and `llm_traces`. Translate usage into the accumulator path or preserve it through the provider response, and add an end-to-end streaming usage assertion.

**Change type:** Provider adapter and integration-test change; no schema migration required for usage fields already present.

### 4.2 Self-hosted BYO credentials cannot route through the proxy

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; blocks self-hosted BYO-provider support.

Auth persistence permits `vllm_self_hosted` at `services/auth/internal/service/provider_credentials.go:26-32`. The proxy constructs the self-hosted adapter using the runtime name `openaicompatible` at `services/proxy/internal/bootstrap/provider.go:312-322`, with the name defined at `packages/provider/openaicompatible/config.go:16-17`. `services/proxy/internal/http/chat_provider.go:130-148` sends the runtime name to Auth, which rejects unsupported names at `services/auth/internal/service/provider_credentials.go:199-203`.

Use one canonical provider identifier or an explicit mapping, then test the complete self-hosted credential and BaseURL path.

**Change type:** Identifier mapping and integration tests; no migration if stored names remain compatible.

## 5. Tokenizer and context-budget accuracy

### 5.1 Tool schemas are emitted after budgeting but excluded from the budget

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Confirmed; blocks tool-enabled context flows near the model window.

`services/context/app/assemble.py:131-151` calculates the budget before passing `request.tool_schemas`. `services/context/app/formatter.py:105-117` appends serialized tool schemas, but `services/context/app/budget.py:55-75` has no tool-schema parameter or token calculation. Formatter tests cover emission at `services/context/tests/test_formatter.py:282-300`, while budget tests at `services/context/tests/test_budget.py:41-108` contain no tool accounting assertion.

A large tool-schema block can make the final prompt exceed the provider context window even when the packer’s budget invariant passes. Include canonical tool-schema serialization in the budget and add an aggregate boundary test.

**Change type:** Context algorithm and test change; no migration.

### 5.2 Budget counts raw content, not the final serialized system/context prompt

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Confirmed; blocks near-limit context assembly.

`services/context/app/budget.py:63-75` estimates raw directive and history. `services/context/app/formatter.py:156-182` adds memory tags, escaping, newlines, safety text, and nonce markers. `services/context/app/packer.py:233-235` estimates only raw memory content, and `services/context/app/assemble.py:186-188` reports raw component totals rather than final serialized size.

Use the canonical serialized representation for budgeting, or conservatively account for every wrapper and escaping overhead. Add boundary tests with directive wrappers, escaped memory text, and full-window prompts.

**Change type:** Context algorithm and test change; no migration.

### 5.3 Exact tokenizer support is unreachable from context-budget calculation

**Severity:** **P2**  
**Classification:** **Implemented-but-unreachable-by-consumer**  
**Status:** Confirmed; follow-up.

`packages/tokenizer/model_count.go:19-47` provides model-aware counting, with implementations at `packages/tokenizer/tiktoken.go:46-53` and `packages/tokenizer/claude.go:24-35`. The Python context path instead imports and calls the estimator at `services/context/app/budget.py:8-9,61-66`. The context README acknowledges approximation and defers exact family counting at `services/context/README.md:5-9`.

Wire supported exact families into the budget consumer while retaining an explicit estimator fallback for unsupported families. The Claude implementation is itself marked as an estimate, so exactness is family-specific.

**Change type:** Cross-language integration and tests; no migration.

### 5.4 Estimator inputs lack the tokenizer hard limit

**Severity:** **P2**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Confirmed; follow-up with an untrusted-input release gate.

`packages/tokenizer/limits.go:3-4` and the tokenizer implementations reject inputs over 100 KiB. `services/context/app/estimate.py:16-38` has no equivalent limit. `services/context/app/server.py:42-46,367-424` bounds selected message fields but not tool schemas, and `services/context/app/clients/directive.py:83-128` plus `clients/memory.py:197-216` show no tokenizer-size limit.

Apply one documented byte/character bound before estimation and formatting to directives, memories, and tools, or route all counting through a bounded tokenizer API.

**Change type:** Validation and resource-hardening change; no migration.

### 5.5 Capability catalog is process-stale

**Severity:** **P2**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Confirmed; follow-up before live capability updates are relied upon.

`services/context/app/capability_catalog.py:81-98` loads model limits and tokenizer policies, while `:101-103` caches the first catalog forever with `lru_cache(maxsize=1)`. The catalog has no content fingerprint at `:19-35,93-97`, and `services/context/app/assemble.py:114-121,206-215` derives budgeting and packing policy from that cached object.

A long-lived worker continues using stale context limits after a model-capability update. Add a catalog version/fingerprint and reload path, with a test that swaps the catalog and verifies new limits take effect.

**Change type:** Runtime configuration lifecycle change; no migration.

## 6. Memory and context-assembly correctness

### 6.1 Configured rank weights are validated but ignored in production scoring

**Severity:** **P1**  
**Classification:** **Implemented-but-unreachable-by-consumer**  
**Status:** Open; blocks truthful dashboard ranking controls.

`services/memory/app/config.py:78-117,228-240` defines and validates `IBEX_RANK_WEIGHT_*`, and `services/memory/app/main.py:199-203` passes settings into the repository. However, `services/memory/app/read/ranking.py:110-112` and `services/memory/app/cache/hot_score.py:15-23` call `composite_score()` without configured weights, invoking hard-coded defaults at `services/memory/app/scoring/composite.py:77-84`.

Pass `RankWeights` through every production scoring call and add a configuration-change ranking test.

**Change type:** Dependency wiring and tests; no migration.

### 6.2 Multi-label memories use only the primary category for decay

**Severity:** **P1**  
**Classification:** **Implemented-but-unreachable-by-consumer**  
**Status:** Open; blocks claims about documented memory-retention behavior.

ADR 0053 requires the minimum half-life for multi-label memories at `web/content/docs/adr/0053-vector-store-abstraction.mdx:52-56`, and the correct sequence-based function exists at `services/memory/app/scoring/half_life.py:29-40`. Labels are persisted at `services/memory/app/routers/memory_write_support.py:240-259`, but read and hot-cache paths pass only `memory.category` at `services/memory/app/read/ranking.py:61-67`, `services/memory/app/read/repository.py:193-210`, and `services/memory/app/cache/hot_score.py:15-23`.

Hydrate all labels or persist an effective minimum half-life and pass it to scoring. Add a factual-plus-episodic integration case.

**Change type:** Read-model/query and scoring change; likely no migration if labels are already queryable, otherwise a read-model expansion.

### 6.3 Bucketed DP can return a lower-value pack after repair

**Severity:** **P1**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; blocks dashboard acceptance criteria that depend on truthful memory selection.

`services/context/app/packer.py:166-184` uses floor bucket weights at `:379-382`; `:262-289` repairs an over-budget selection by dropping the lowest-value selected item and greedily refilling without exact re-optimization. A concrete counterexample is a budget of 32 with a 31-token item scoring 0.90 and two 16-token items scoring 0.60 each: the exact optimum is the two 16-token items at 1.20, but lossy bucket selection and repair can retain the 0.90 item. Existing coverage at `services/context/tests/test_packer.py:427-437` does not exercise this mixed-size case.

Use conservative ceiling buckets or exact-token optimization, retain exact-budget validation, and add a brute-force oracle for mixed-size candidates.

**Change type:** Algorithm and test change; no migration.

### 6.4 DP cell ceiling undercounts the allocated matrix

**Severity:** **P2**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; follow-up.

The guard uses `n * (buckets + 1)` at `services/context/app/packer.py:171-184`, while the DP allocation uses `(n + 1) * (buckets + 1)` at `:337-342`. Tests encode the same undercount at `services/context/tests/test_packer.py:396-405`, and the setting is documented as a safety ceiling at `services/context/app/config.py:111-118`.

Compute the guard with the actual allocation dimensions and test the exact ceiling and first-over-ceiling cases.

**Change type:** Algorithm guard and tests; no migration.

## 7. Observability, error handling, and operations

### 7.1 API readiness becomes stale after startup

**Severity:** **P1**  
**Classification:** **Documented-but-unimplemented**  
**Status:** Open; **blocks production-facing dashboard rollout**.

`web/engineering/OPS_GUIDE.md:16-20` documents `/ready` as checking critical external dependencies. In implementation, `services/api/app/main.py:227-258` refreshes readiness only during lifespan startup, `:276-289` stores the result, and `services/api/app/probes.py:18-32` returns the stored state without a live check. Tests at `services/api/tests/unit/test_main_lifespan.py:15-24,62-79,81-105` cover startup failure but not post-start dependency loss or recovery.

If Auth gRPC or Postgres fails after startup, the API can continue returning HTTP 200 from `/ready`, so orchestration can keep routing traffic to an unhealthy process. Add bounded runtime checks or a bounded background refresh, transition ready false on failure and true on recovery, and add integration tests for loss and recovery.

**Change type:** Service lifecycle/probe implementation and integration tests; no migration.

### 7.2 Security-integration CI covers only Go proxy paths

**Severity:** **P2**  
**Classification:** **Undocumented-but-real bug**  
**Status:** Open; blocks release of an authenticated dashboard, not necessarily a public static shell.

`.github/workflows/ci.yml:733-737` scopes the security-integration job to Go changes, and `:777-787` runs only `TestSecurity_*` under `./services/proxy`. API and MCP tests run separately as unit jobs at `:977-1014,1042-1066`, while web build/tests at `:1717-1837` have no authenticated security integration. `services/proxy/proxy_security_sec7_agent_pause_test.go:46-62` confirms the exercised path is proxy-centric.

Add cross-tenant denial, revoked/invalid credential, fail-closed, secret-safe-error, API/MCP authorization, and dashboard-auth tests to the security gate. If the dashboard is intentionally public, document and test that boundary explicitly.

**Change type:** CI/test-surface expansion; no migration.

## Cross-cutting concerns not covered by the seven angles

The following should be tracked because they affect the safety of any dashboard built on this stack:

1. **Contract capability drift.** Several proto or roadmap surfaces advertise fields or methods that silently default or return `UNIMPLEMENTED`. Track D should consume explicit capability/version metadata rather than infer support from descriptors alone.
2. **Security-boundary duplication.** Provider validation in the API but not at Auth or proxy use demonstrates a general risk: a management-path check is not a system invariant unless enforced at the persistence or consumption boundary.
3. **Historical reproducibility.** The prior trace audit found missing raw payloads and context joins. The new pricing/model-version and Anthropic streaming findings reinforce that dashboards cannot explain historical behavior unless immutable provider/model/usage snapshots are persisted at write time.
4. **Release gates do not match surface area.** Security integration and readiness checks are proxy/startup-centric while Track D adds API, MCP, and dashboard surfaces. The test and probe boundaries must expand before treating dashboard health as production evidence.

## Master checklist

The checklist is ordered by severity and then blast radius. **BLOCKS START** means the corresponding Track D implementation or rollout should not begin or ship without closure. **FOLLOW-UP** means work can proceed only with the scope caveat recorded.

1. **P1 — BLOCKS START:** Close plaintext provider-secret disclosure in `services/auth/internal/grpc/provider_credentials.go:58-83`; require a narrowly scoped service authorization and prevent chat/agent bearer tokens from receiving decrypted credentials.
2. **P1 — BLOCKS START for BYO-provider paths:** Enforce BaseURL SSRF policy at the Auth write boundary and proxy consumption path; eliminate private-destination, redirect, DNS-rebinding, and TOCTOU exposure.
3. **P1 — BLOCKS START for production rollout:** Replace startup-only readiness at `services/api/app/main.py:227-289` and `services/api/app/probes.py:18-32` with bounded runtime checks and failure/recovery integration tests.
4. **P1 — BLOCKS START for tool-enabled context flows:** Include serialized tool schemas and formatter overhead in context budgeting; add near-window boundary tests.
5. **P1 — BLOCKS START for truthful memory-ranking controls:** Pass configured rank weights through read and hot-cache scoring and preserve all labels needed for minimum half-life semantics.
6. **P1 — BLOCKS START for memory-selection acceptance:** Correct the lossy bucketed DP repair path or replace it with conservative/exact optimization; add the mixed-size counterexample and brute-force oracle.
7. **P1 — FOLLOW-UP:** Fix self-hosted provider identifier mismatch before enabling self-hosted BYO credentials.
8. **P1 — FOLLOW-UP:** Release idempotency claims on cancellation and detect replay before session mutation.
9. **P1 — FOLLOW-UP:** Preserve Anthropic streaming usage metadata before releasing usage or cost analytics for Anthropic streams.
10. **P2 — BLOCKS RELEASE of an authenticated dashboard:** Expand security integration beyond Go proxy tests to API, MCP, and dashboard authorization surfaces.
11. **P2 — BLOCKS START only if exposed by Track D:** Implement or version-gate context budget/ranking controls and the `SearchMemories`/`RecordMemoryFeedback` RPCs.
12. **P2 — FOLLOW-UP:** Implement real MFA verification/freshness or remove the overstated `X-MFA-Code` contract before directive mutation workflows ship.
13. **P2 — FOLLOW-UP:** Make Buf breaking checks required and failure-propagating before expanding v1 proto contracts.
14. **P2 — FOLLOW-UP:** Implement `month_tokens` accounting or remove/narrow the documented monthly-quota promise.
15. **P2 — FOLLOW-UP:** Wire supported exact tokenizer families into context budgeting, impose aligned input-size limits, and add capability-catalog invalidation.
16. **P2 — FOLLOW-UP:** Correct the DP ceiling to `(n + 1) * (buckets + 1)` and test the boundary.
17. **P3 — FOLLOW-UP:** Reconcile proto-generation comments in `packages/proto/buf.gen.yaml`, ADR 0004, and the CI/README behavior.

## References

All evidence cited in this report is from the audited repository at the revision stated above. The prior trace-inspector report is the baseline used to exclude already-known findings.

[1]: `services/auth/internal/grpc/provider_credentials.go` "Provider credential gRPC handlers"
[2]: `services/auth/internal/service/provider_credentials.go` "Provider credential service"
[3]: `services/proxy/internal/credentials/resolver.go` "Proxy provider credential resolver"
[4]: `packages/permissions/permissions.go` "Permission definitions and checks"
[5]: `services/api/app/services/providers.py` "Provider management service"
[6]: `services/api/app/services/provider_validate_net.py` "Provider destination validation"
[7]: `services/proxy/internal/http/chat_provider.go` "Proxy provider request path"
[8]: `packages/provider/openaicompatible/client.go` "OpenAI-compatible provider client"
[9]: `packages/provider/anthropic/client.go` "Anthropic provider client"
[10]: `services/proxy/internal/http/chat/idempotency.go` "Proxy idempotency lifecycle"
[11]: `packages/idempotency/store.go` "Idempotency store and pending-claim TTL"
[12]: `services/proxy/internal/http/chat_session_bridge.go` "Proxy session bridge"
[13]: `services/proxy/internal/http/session/lifecycle.go` "Proxy session lifecycle"
[14]: `web/content/docs/adr/0035-chat-idempotency-key.mdx` "Chat idempotency contract"
[15]: `packages/ratelimit/hierarchical.go` "Hierarchical rate limiter"
[16]: `web/content/roadmap/phase-4-multi-provider/milestones/4.b.1-lua-hierarchical-rate-limiter.mdx` "Hierarchical limiter roadmap"
[17]: `packages/proto/proto/ibex/context/v1/context.proto` "Context Assembly protobuf contract"
[18]: `services/context/app/server.py` "Context Assembly gRPC server"
[19]: `packages/contextclient/types.go` "Context client request types"
[20]: `services/context/app/assemble.py` "Context assembly orchestration"
[21]: `services/context/app/budget.py` "Context budget calculator"
[22]: `services/context/app/formatter.py` "Context formatter"
[23]: `services/context/app/packer.py` "Context memory packer"
[24]: `services/context/tests/test_packer.py` "Context packer tests"
[25]: `packages/provider/anthropic/stream_translate.go` "Anthropic stream translator"
[26]: `packages/provider/anthropic/retry.go` "Anthropic provider retry wrapper"
[27]: `packages/provider/openaicompatible/stream_accumulator.go` "OpenAI-compatible stream accumulator"
[28]: `services/proxy/internal/http/stream_forward.go` "Proxy stream forwarding"
[29]: `services/proxy/internal/bootstrap/provider.go` "Provider registry/bootstrap"
[30]: `packages/provider/openaicompatible/config.go` "OpenAI-compatible provider identifiers"
[31]: `packages/tokenizer/model_count.go` "Model-aware tokenizer registry"
[32]: `packages/tokenizer/tiktoken.go` "Tiktoken tokenizer"
[33]: `packages/tokenizer/claude.go` "Claude tokenizer estimate"
[34]: `services/context/app/estimate.py` "Context token estimator"
[35]: `services/context/app/capability_catalog.py` "Context capability catalog"
[36]: `services/memory/app/config.py` "Memory service configuration"
[37]: `services/memory/app/read/ranking.py` "Memory read ranking"
[38]: `services/memory/app/cache/hot_score.py` "Memory hot-cache scoring"
[39]: `services/memory/app/scoring/composite.py` "Memory composite scoring"
[40]: `services/memory/app/scoring/half_life.py` "Memory half-life scoring"
[41]: `services/memory/app/routers/memory_write_support.py` "Memory label persistence"
[42]: `services/memory/app/read/repository.py` "Memory read repository"
[43]: `services/api/app/main.py` "API lifecycle and readiness"
[44]: `services/api/app/probes.py` "API readiness probe"
[45]: `services/api/tests/unit/test_main_lifespan.py` "API lifecycle tests"
[46]: `.github/workflows/ci.yml` "Continuous integration workflow"
[47]: `.github/branch-protection-main.json` "Main branch protection checks"
[48]: `web/engineering/OPS_GUIDE.md` "Operational readiness guidance"
[49]: `web/engineering/API_DOCUMENTATION.md` "API documentation"
[50]: `web/content/docs/adr/0004-protobuf-and-codegen-policy.mdx` "Protobuf and codegen policy"
[51]: `packages/proto/buf.gen.yaml` "Buf generation configuration"
[52]: `packages/proto/README.md` "Proto package README"
[53]: `web/content/docs/adr/0038-context-assembly-service.mdx` "Context assembly service ADR"
[54]: `web/content/docs/adr/0053-vector-store-abstraction.mdx` "Vector-store and half-life ADR"
[55]: `web/content/roadmap/phase-4-multi-provider/milestones/4.d.4-drift-alerts-directive-management.mdx` "Drift alerts and directive management milestone"
