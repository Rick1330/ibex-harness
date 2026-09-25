# Pre-Track-D Readiness: Three-PR Remediation Plan

**Baseline reviewed:** `a041ed302bfc7966d94b6ce175fec655ced5263c` (`main`, 2026-09-24)
**Plan purpose:** Close the minimum source, identity, topology, and assurance prerequisites before beginning a real Track D product slice.
**Scope warning:** These three PRs are a **readiness series**, not a promise to close every Phase 4 P/D/E milestone. D2–D6 each retain their own backend, privacy, and P6 slice gates; Track E remains a separate release-evidence path.

## Decision and order

Proceed in three independently reviewable PRs:

1. **PR 1 — Fail-closed runtime controls and protected regression gates.** Remove production bypasses for model-policy and rate-limit dependency failures; require an explicit Proxy runtime profile and shared Redis outside development; make the Python and custom-rule Semgrep results protected merge contexts; test active/inactive/failing/skipped-only gate semantics. This is the branch-ready stage being implemented first.
2. **PR 2 — Mounted identity/session and authorization assurance.** Close the route-level P1 gaps: production RS256/session requirements, actually mounted step-up for high-impact actions, explicit route permissions and resource scope, and mounted four-role/two-tenant HTTP negatives. This must not be described as full P1 closure until revocation and runtime evidence pass.
3. **PR 3 — P0 runtime proof, D0 boundary, and P6-bootstrap.** Implement/verify the canonical topology and its environment configuration, console fixture/build/accessibility baseline, OpenAPI/client/parser contracts, evidence manifest, applicability-aware required checks, and a real authenticated staging smoke with rollback. External staging, ingress/TLS, secret-management, and review/owner decisions are dependencies, not facts this PR can manufacture.

The Phase 4 dependency graph is `P0 → P1 → (D0 ∥ P6-bootstrap) → D1`. Consequently, **the D1 implementation must not start merely because these PRs merge**. The P0/P1 evidence and D0/P6-bootstrap acceptance gates listed below must be recorded against the canonical environment first. This sequence does not authorize D2–D6 or E1–E4.

## Current reality at the reviewed baseline

| Area | What exists | What remains true / consequence |
|---|---|---|
| Console | `services/console` is a real Next.js package with runnable quality scripts. A multi-flag preview gate preserves fail-closed behavior; when enabled, the UI labels itself preview-only. | It is not a live operator console: AuthService is disconnected, analytics are fixtures, Overview is simulated, and production is unavailable by default. Existing D0 quality and fixture containment are useful partial evidence, not D0 completion or D1 evidence. Reconcile the README's reachability wording with actual routing before any runtime smoke claim. |
| D0/D1 | The canonical package boundary and D1 scope are specified. | D0 exit still needs canonical ownership, quality/accessibility/security evidence, compatibility/retirement criteria, and a D1 entry contract. D1 still needs server-derived context, a real Overview contract, freshness/data states, health, SSE, navigation/URL state, route tests, and rollback. |
| P0 | ADR-0078, an environment/origin matrix, and smoke artifacts exist. The accepted intended boundary is `services/console`, public docs on Pages, and API/workers/data plane in the runtime platform. | ADR-0078 calls staging/production origins planned and no API Ingress provisioned. The checked-in smoke uses a local environment/in-process stubs; it is not a deployed login/API/SSE/rollback transcript. Restore artifacts are repository evidence, not measured production PITR/RPO/RTO or Kyverno admission. Proxy also previously defaulted missing `IBEX_ENV` to development; PR 1 removes that source-level ambiguity, while P0 must still verify actual staged values. P0 remains provisional. |
| P1 | Auth/API routes, RS256 issuance/verifier pieces, cookie/CSRF middleware, RLS, permission helpers, session replay protection, and operator SSE tests exist. | Route helpers are not proof of mounted enforcement. The step-up probe is defined but legal-hold mutation routes do not use it; such requests deny because the required request state is never populated. HMAC fallback, JWT-header algorithm validation/key rotation, access/step-up revocation, production cookie policy, and route-level role/tenant coverage remain unclosed. P1 is mounted-but-provisional. |
| P2 evidence | Postgres evidence tables/outbox, typed identity foundations, Redis relays, and ClickHouse projections exist. | Proxy publication is fail-open for chat and can lose records; crash-after-sink-before-ack idempotency is not proven; query DTOs/source watermarks and unavailable-vs-empty semantics are incomplete. This blocks authoritative D2 claims, not the act of coding D1. |
| P3 privacy/lifecycle | Capture modes, encrypted object writes, audit/deletion foundations, holds, and multi-store worker tests exist. | Open questions include configured-store absence, redaction/archive failure reporting, orphan capture objects, receipts surviving purge, hold/delete races, ClickHouse TTL under hold, worker/backup/DLQ coverage, and authorized receipt reads. D3/D4 need closure; do not fold raw-content, replay, or deletion UI into D1. |
| P4 usage/cost | Usage fact writer, estimates, bounded organization-scoped queries, and billing schema are present. | `spent_cents_cached` is an estimate projection, not reconciled actual spend. There is no authoritative invoice source (`#859` remains open), canonical fact identity/deduplication/reconciliation, source watermark, or hard-cap admission proof. No unlabelled spend or hard-cap control belongs in D1. |
| P5/runtime | Helm, migration SQL/job templates, restore scripts, digest-policy text, and honest restore artifacts exist. | No console workload or API Ingress/TLS template is present; image digests are placeholders, migration job disabled, migration image/secret contract unresolved, and restore evidence uses pg_dump fallback with `rpo_pass=false`; Kyverno was not applied. ADR-0078's Pages-only UI decision must be reconciled with P5 wording. |
| P6/E | Specifications for P6 and E1–E4 exist; GitHub branch protection requires the repo, Go, web, and security aggregate gates. | P6 bootstrap/slice manifests and immutable operator E2E bundles were not found. `ci-gate-python` exists but is not protected. Semgrep custom rules hard-fail within its workflow but lack a required aggregate; community rules are advisory/SARIF. A skipped path-scoped area is intentional scoped CI, not per se a test pass; P6 still needs an explicit applicability/missing-check manifest. E1–E4 are planned/specification, not completed. |
| Roadmap freshness | Multiple reports, ADRs, milestones, and design audits document substantial work. | Re-baseline documents: PR #873 is now merged, while F4-028/029/030 still say pending merge; issue #846 is open, #853 closed, #859 and #869 open. The readiness report's local pytest failure means prior API test status was **unverified**, not failed/passed. Milestone prose and old smoke logs must not outrank current source and dated evidence. |

The detailed readiness assessment and cross-cutting audits remain useful source material, but recommendations to “seed/add `services/console`” are stale because that package now exists. Likewise, P0/P5 artifact *existence* must not be confused with runtime closure. Record baseline SHA, test commands, outputs, and artifact identity for each new claim.

## PR 1 — Fail-closed runtime controls and protected regression gates

### Goal and boundary

Make a policy-store or limiter outage incapable of silently authorizing paid-provider traffic or bypassing organization model policy. Protect the Python and existing custom Semgrep security regression suites with required aggregate checks. This is a safety PR, not an operator UI or full identity milestone. Preserve the preview-only console path.

### Implementation scope

- Delete `PassthroughRegistry` from production code and remove `IBEX_MODEL_POLICY_ALLOW_PASSTHROUGH` as an operational control. If the legacy environment variable is set to true, reject startup with a clear migration error rather than silently accepting it. Nil/missing Postgres or missing policy dependencies must choose deny-by-default; a policy dependency outage should produce the defined **503/degraded** result, not an ordinary 403 that misrepresents infrastructure failure.
- Change Proxy rate-limit middleware from “warn and continue” to fail closed when the configured shared limiter returns an infrastructure error. Return the documented service-degraded 503, increment the error metric, do not invoke chat/provider work, and never label infrastructure failure as a quota 429. Reject unset/empty `IBEX_ENV` before applying defaults and reject `REDIS_URL` absence outside development so a misconfigured deployment cannot silently select development/Noop behavior. Wire the canonical Helm chart's local/staging/production profiles explicitly and require its out-of-band Redis Secret in non-development renders. No emergency local fallback is introduced without a separate, reviewed global-capacity design.
- Preserve test isolation using explicit test-only fake resolvers/limiters; do not keep a production package-level bypass merely because old router tests used it.
- Add `ci-gate-python` to `.github/branch-protection-main.json`. Add a `ci-gate-semgrep` aggregate workflow that runs the custom hard-gate rule scan when relevant and is a required status context. Keep community/OWASP findings explicitly advisory until they have triaged severities and false-positive policy; do not silently redefine every community finding as a blocker.
- Add deterministic gate regression tests for detector success/failure/missing, active/inactive, missing child, active failure, unknown/cancelled, and skipped-only statuses; every shared aggregate passes detector status into the same evaluator. Add a repo guard proving required-check inventory names Python/Semgrep jobs with matching emitted names and detector plumbing. An active gate requires at least one successful applicable child while allowing scoped skips. Keep actual external GitHub branch-protection application distinct from editing the desired-state file.
- Update ADR-0075, the environment-variable inventory, F4-015/F4-034 wording, and proxy tests so no documentation claims a supported fail-open escape hatch or claims the live GitHub settings changed before they do.

### Required tests/evidence

- Proxy bootstrap tests: nil PostgreSQL, nil provider registry, and legacy bypass flag all deny; model policy is disabled in metrics and warning logs identify the reason without exposing secrets.
- Mounted chat-router test: unavailable policy returns 503 and never reaches a provider; explicitly denied model remains 403; unregistered model retains its distinct provider-not-configured behavior.
- Rate-limit middleware tests: Redis failure returns 503/degraded, does not call downstream chat, increments the failure metric, and does not return 429; normal allowed and exhausted-quota behavior remains unchanged.
- Config tests prove the old bypass setting cannot restore permit behavior (fail-fast on `true`; false/unset cannot activate it), an empty/unset environment is rejected, and non-development configuration requires `REDIS_URL`, while an explicitly selected development profile retains Noop behavior.
- Helm schema/render checks prove the local chart profile is explicit development with an optional Redis Secret, while staging and production render explicit profiles and a required `ibex-redis` Secret reference. Rendering does not prove that credentials exist or are healthy in a cluster.
- CI gate tests cover detector failure/missing, active failure, active success, inactive/inapplicable path, missing child, skipped child, and failure/unknown status; required-check inventory contains only names actually emitted by workflows and the Python/Semgrep gates pass detector outcomes to the common evaluator.
- Run targeted Go package tests and lint/format checks; capture complete CI gate results. Verify runtime GitHub branch protection separately after authorized application; source JSON is not proof of live configuration.

### Explicit exclusions

No broad rate-limit redesign/emergency local token bucket, full Python/Semgrep rule tuning, provider SSRF redesign, model-policy durable invalidation redesign, chat-idempotency-store redesign, console live connection, secret/key rotation, or production environment promotion. Any finding outside this exact safety boundary stays in the risk register with owner, disposition, and gate.

### Completion claim

When merged and tested, claim only that these two runtime outage paths fail closed and the protected CI configuration *is declared* in source. Do not claim P0/P1, P6, or live GitHub branch-protection closure without their own evidence.

## PR 2 — Mounted identity/session and authorization assurance

### Goal and boundary

Make the API's security contract inspectable and enforce it on mounted routes before the console consumes them. PR 1's provider fail-closed controls and Python/security regression gates are prerequisites. This PR does not add console screens or start P6-bootstrap/D0 before the roadmap's P0→P1 order allows them.

### Implementation scope

- Establish production-only AuthService RS256 validation as the only operator session path. Validate JWT header algorithm as RS256, key type, issuer/audience/token kind, expiry, and rotation/key identification. Remove or fail production boot on HMAC fallback. Define the session lifecycle for refresh, replay/family revocation, logout, access-token revocation, and step-up JTI expiry/replay; implement mounted semantics rather than relying only on issuer/store helpers.
- Mount ordered step-up verification for legal-hold set/clear and any already-classified high-impact operator mutation. Bind it to verified subject, organization, session, action, and freshness; consume it once and emit an audit identity/receipt. Missing, expired, replayed, wrong-org/subject/session/action must deny. Avoid wiring the same mutable request-state flag in two unordered dependencies.
- Publish an explicit route-policy inventory for token, billing, provider, model policy, capture policy, legal hold, organization lifecycle, platform metadata, SSE, and session endpoints. State role, permission bit, resource/action scope, owner/admin boundaries, anti-enumeration response, and step-up requirement for each read/mutation. Route declarations and service checks must agree; helpers alone do not satisfy it.
- Test mounted HTTP APIs with viewer/operator/admin/owner across two organizations; cover no auth, missing permission, foreign organization direct IDs/search/deep-links, guessed IDs, disabled/unavailable publisher/queue/policy store, and session revocation. Verify tenant context is derived from AuthService rather than query/header/client state.
- Verify cookie and browser boundary against ADR-0078: `Secure` outside local, `HttpOnly`, approved `SameSite`/domain/path, exact credentialed CORS origin list, strict Origin/Referer where required, double-submit CSRF on every cookie-authenticated mutation, and sensitive response `no-store`.
- Add OpenAPI/runtime-route inventory assertions for the protected endpoints so mounted-but-undocumented routes fail CI.

### Required tests/evidence

- Go verifier tests reject `alg:none`, HS256, altered `alg`, wrong key type, invalid issuer/audience/kind, expired/unknown/rotated keys. API integration confirms no HMAC operator session can be established in staging/production mode.
- Mounted FastAPI TestClient authorization matrix: four roles x two organizations, per-route allow/deny, Org B direct lookup returns the approved anti-enumeration 404/empty result, missing/expired/replayed/mismatched step-up denies, correct step-up succeeds, and missing required dependency returns a documented unavailable response.
- Refresh replay revokes family; logout/access/step-up behavior is asserted; cookie flags, CSRF, exact-origin CORS, and no-store response headers have contract tests.
- Legal-hold set/clear verifies the captured step-up JTI/audit outcome, cross-store hold/delete race negative tests are included where the service contract exists, and a missing probe cannot report success.
- Tests must run with real service dependencies where milestone requires them. TestClient/fakes are explicitly labeled contract evidence only, not deployed P1 closure.
- Update P1 route-by-route matrix with each row tagged implemented, mounted-tested, runtime-tested, or blocked; retain open state for anything not exercised.

### Explicit exclusions

No D1 Overview or BFF, trace/raw content read APIs, replay, incident/evidence-bundle workflow, directives, actual billing reconciliation or hard caps, broad RLS redesign, deletion-saga redesign, provider public-egress policy implementation, or staging/production promotion. Those remain governed by P2–P5 and their named D slices.

## PR 3 — Canonical runtime proof, D0 boundary, and P6-bootstrap

### Goal and external prerequisites

Close the P0/D0/P6-bootstrap entry contracts after P1 is available, and provide reproducible evidence that the intended console/API session boundary runs in the canonical topology. This PR may prepare infrastructure/configuration and tests, but the P0 exit result remains blocked until named operators provision and exercise the real staging/API ingress, TLS, secret delivery, and rollback environment.

### Implementation scope

- Reconcile the accepted ADR-0078 boundary (`services/console` is the canonical UI, Pages may host immutable UI assets, Helm owns API/data plane) with P0/P5 milestone prose. Publish final ownership/origin matrix for local, preview, staging, production: UI/API/SSE origins, TLS, cookie/CORS/CSRF, CSP `connect-src`, proxy buffering/write/idle timeout, secrets/key rotation, cache rules, and rollback owner. Mark the current planned hostnames as unprovisioned until a real endpoint is checked.
- Implement CI Helm lint/template checks across supported overlays. Reject placeholder image digests. Validate API routing/secret refs/readiness/migration contract; provide a pinned migration artifact or a reviewed, explicit external mechanism. Run migration compatibility on disposable Postgres with N/N+1 and forward-fix semantics; do not use destructive `down` as the deployment rollback.
- Keep the canonical console fail-closed and classify every route as live, preview-only, deferred, or unavailable. Reconcile README inaccuracies; record compatibility status and retirement criteria for `services/dashboard`; prove production/default route cannot render fixture data. Complete D0 shell lint/type/test/build, stable visual baseline, axe/keyboard/reduced-motion/zoom checks and artifact capture.
- Implement the P6-bootstrap interfaces: pinned environment and fixture/schema versions; OpenAPI snapshot and generated-client freshness; runtime DTO validation (security-sensitive unknown/malformed shapes rejected); immutable evidence manifest including SHA, image/artifact digest, environment/topology, fixture/schema/migration IDs, commands, timestamps, expected/applicable/skipped checks/reasons, thresholds, result, artifact links, rollback digest/config, and owner; required-check inventory parity with both workflow names and live branch-protection evidence. An inapplicable path is explicitly recorded; missing expected evidence is not a pass.
- Build the canonical server-capable Playwright harness and artifact collector. At this bootstrap stage exercise shell/auth/session/context/health/SSE only as corresponding real contracts become available. Produce JUnit, traces, screenshots/video, axe, visual diff, tenant-negative, parser, performance, security and rollback outputs; avoid calling local TestClient/fakes “operator E2E.”
- Provision/run a real staging smoke: login/me, API, origin/cookie/CSRF negatives, session expiry/revocation, tenant denial, SSE connect/Last-Event-ID reconnect/no duplicates/slow-client/drain, dependency-aware health, and rollback to the prior UI/API digests with compatible schema/config. Attach the same immutable identity to every output. Public documentation must remain independently available during operator rollback.
- Record a D1-entry decision with three separate columns: blockers to start D1, blockers to complete D1, and later-slice/release blockers. Each accepted residual risk has an owner, expiry/review date, mitigation and rollout limit.

### External closure evidence required

- DNS/Ingress/TLS and SSE proxy behavior have been provisioned and verified; no “planned hostnames” remain in the environment claiming closure.
- External secret manager ownership, rotation, and staging values are real and verified without placing secrets in Git or `NEXT_PUBLIC_*`.
- Runtime transcript proves authenticated API/SSE and route rollback using commit/image/artifact digest, schema, fixture, environment, command, timestamps and artifact links.
- Live branch protection matches declared inventory. GitHub settings changes are applied by an authorized owner; a checked-in JSON file alone is not proof.
- No test skips that were expected in the staging profile; all residuals and absent dependencies are explicit.

### Explicit exclusions

No live Overview cards/metrics, D1 workbench, trace inspector, raw conversation content, replay, incidents, directives, or billing governance. Passing Helm lint, a static Pages build, accessibility scan, or local smoke does not close P0, P1, P6, D0, D1, P5, or Track E by itself. PITR/RPO/RTO, Kyverno admission, chaos, staged rollout, and E1–E4 remain separately evidenced gates.

## Gap disposition so none is silently dropped

| Gap / finding | Disposition in this series | Downstream gate or milestone |
|---|---|---|
| Model-policy fail-open environment escape hatch (F4-015); dependency failures should be unavailable, never allowed | **PR 1** | P1 evidence remains open until runtime and route matrix pass. |
| Missing Proxy profile defaults to development and weakens production guards (F4-036) | **PR 1:** require explicit `IBEX_ENV` | P0 still verifies staged values and deployment ownership. |
| Redis-backed Proxy rate-limit fail-open (F4-037) | **PR 1:** require Redis outside explicit development; fail closed with 503 and do not call provider | Further local emergency cap design only if explicitly approved; chaos/outage proof under E2. |
| Python aggregate absent from live required checks; custom Semgrep aggregate not protected (F4-034) | **PR 1:** declare required aggregators and add parity regression | External apply and verification owner; community rules remain advisory pending triage. |
| Step-up probe exists but not mounted; JWT alg/key/rotation/HMAC/revocation and explicit route permission matrix | **PR 2** | Full P1 depends on runtime/P6 evidence and P0 topology. |
| Provider credential scope/SSRF, model-policy invalidation, organization deletion/holds, embedding recovery/tenant-safe ANN, readiness/task bounds | Some foundations and tests exist; re-verify at route/runtime level; mark each residual fixed, blocked or risk-accepted before D1 | P1/P2/P3/P5; no UI-based closure. |
| Context budgeting, configured rank weights, multi-label half-life/packer correction (F4-028/029/030) | **Already merged:** PR #873 on 2026-09-20; remove stale “pending merge” wording when attaching its evidence; note residual hot-cache ordering if still applicable | P2/P6 evidence remains according to actual tests. |
| Embedding profile/version persistence and pre-score truncation (F4-031) | Not silently folded into D1; assign owner/evidence before memory-dependent slice | P2/D3; tenant-safe retrieval is a D1 gate if Overview queries memory. |
| Evidence projection loss, idempotency/watermarks/query DTOs | Not D1 scope; no evidence view may present partial/empty as authoritative | P2/P6 before D2. |
| Redaction failure success, orphan full-capture objects, receipts deleted with jobs, cross-store hold/delete race, TTL/backup/DLQ erasure | Security/data lifecycle review and D3/D4 contract; no raw-data UI before closure | P3 before D3/D4; release risk disposition as needed. |
| Usage estimate mislabeled actual, non-idempotent fact ingest, no invoice reconciliation or hard-cap proof (#859 open) | Keep estimate-only/advisory or hidden; never enable hard caps in these PRs | P4/D6 plus capacity/reconciliation tests. |
| No Ingress/TLS/console runtime, placeholder digests, disabled migration job, unowned Secrets, weak rollback, incomplete PITR/Kyverno | Define/provision/evidence with named infrastructure owner; PR 3 can supply guards but cannot fabricate external results | P0/P5 and E2/E3; #869 remains open. |
| P6 artifacts missing, scoped CI skipped/no-op semantics, no branch-protection parity; zero required approving reviews in current protection | Implement manifest/bootstrap/parity; record review-governance decision without silently changing live branch rules | P6 bootstrap; authorized GitHub configuration owner. |
| D0/D1 evidence; static console and preview fixtures not live integration | D0 and P6-bootstrap only after P0/P1; then a separate D1 vertical slice | D1 entry/completion acceptance. |
| Trace/memory/replay, incidents/evidence bundles, directives/actions, usage/cost/capacity | Explicitly excluded from this three-PR readiness series | D2–D6, each after its P contract + per-slice P6. |
| Resilience/restore/promotion/signoff | Explicitly excluded; local smoke and prose are not release evidence | E1–E4 after D/P evidence. |

## D1 start gate after all three PRs

Begin D1 only after the owner can point to all of the following, tied to one approved revision/environment:

1. **P0:** canonical runtime and environment matrix, real TLS/origins/cookie/CSRF/CORS/SSE policy, login/API/SSE reconnect/drain transcript, rollback/digest evidence, named owners.
2. **P1:** AuthService RS256 lifecycle/revocation, server-derived tenant on every relevant path, mounted route permissions and step-up, four roles across two tenants, and dependency/tenant-denial evidence.
3. **D0:** canonical console ownership; route classification; no production fixtures; build/type/lint/test, visual/accessibility evidence, compatibility and retirement gate.
4. **P6-bootstrap:** OpenAPI/client/parser and fixture/schema contracts, immutable manifest, required-check/applicability semantics, rollback-record interface, and current branch-protection parity evidence.
5. **Risk disposition:** every cross-cutting P0/P1 affecting operator reads or rollout (provider secret/SSRF, fail-closed policy, tenant-safe memory/query, deletion/hold integrity, bounded maintenance/readiness, SSE/load shedding, supply-chain/recovery) is fixed or explicitly accepted by a named owner with a restriction that prevents an unsafe rollout. A risk entry is not a fix.

D1 completion then additionally requires a real context and Overview DTO/API, real health/freshness/completeness/partial/stale/degraded/empty/error states, session/organization behavior, SSE state/reconnect, URL/navigation behavior, four-role/two-tenant browser journeys, accessibility, no-fixture production assertion, operator-origin smoke and rollback. D1 must not report D2 evidence, actual cost, or lifecycle governance merely because those routes or navigation labels exist.

## Ongoing evidence and roadmap hygiene

For every PR, update only the status supported by merged code plus reproducible evidence. Distinguish `specified`, `implemented`, `mounted`, `contract-tested`, `runtime-tested`, `staging-verified`, `production-observed`, and `accepted residual risk`. Link immutable outputs and identify omissions. Update dated reports at the commit actually tested. Use issues/PRs for external dependencies and owners. Do not interpret issue closure, a green inactive-path aggregate, a route mount, a helper, a migration pair, or a mocked test as milestone closure.

## Source documents

- [Phase 4 dependency graph and exit criteria](/roadmap/phase-4-multi-provider)
- [P0 runtime topology milestone](/roadmap/phase-4-multi-provider/milestones/4.p.0-runtime-topology-environment-contract)
- [P1 identity and authorization milestone](/roadmap/phase-4-multi-provider/milestones/4.p.1-identity-tenancy-authorization-assurance)
- [P2 evidence plane milestone](/roadmap/phase-4-multi-provider/milestones/4.p.2-canonical-evidence-durable-publication)
- [P3 privacy and lifecycle milestone](/roadmap/phase-4-multi-provider/milestones/4.p.3-privacy-retention-deletion-audit)
- [P4 query/usage/cost milestone](/roadmap/phase-4-multi-provider/milestones/4.p.4-query-usage-cost-data-platform)
- [P5 production platform/recovery milestone](/roadmap/phase-4-multi-provider/milestones/4.p.5-production-platform-recovery-supply-chain)
- [P6 assurance harness milestone](/roadmap/phase-4-multi-provider/milestones/4.p.6-contract-assurance-harness)
- [D0 console foundation](/roadmap/phase-4-multi-provider/milestones/4.d.0-canonical-console-foundation-shell-migration)
- [D1 authenticated shell and Overview](/roadmap/phase-4-multi-provider/milestones/4.d.1-authenticated-shell-operational-overview)
- [Console deep readiness plan](CONSOLE_DEEP_READINESS_PLAN.md)
- [Current Track D readiness assessment](PHASE4_TRACK_D_READINESS.md)
- [Operator runtime topology ADR](/docs/adr/0078-operator-runtime-topology)
- [Per-organization model policy ADR](/docs/adr/0075-per-org-model-routing-policy)
- [Cross-cutting operator-platform audit](../research/operator-platform/04-world-class-cross-cutting-audit-before-track-d.md)
- [Operator platform architecture](../OPERATOR_PLATFORM_ARCHITECTURE.md)
- [Security CI gate inventory](../SECURITY-CI-GATES-DELIVERABLES.md)
- [Environment variable inventory](../ENVIRONMENT_VARIABLES.md)
- [Findings register](/roadmap/phase-4-multi-provider/findings)
- [Risk register](/roadmap/phase-4-multi-provider/risks)

---

**Stage status:** PR 1 implementation is open as [#897](https://github.com/Rick1330/ibex-harness/pull/897) from `fix/IBEX-895-pre-track-d-stage1-deny-by-default-assurance`; it remains unmerged and awaits review/hosted CI. No P0/P1/P6, D0/D1, Track D, or Phase 4 closure is claimed by this plan or the branch.

**Important external decision:** The live main-branch rule currently requires six statuses (`ci-gate-repo`, `ci-gate-go`, `ci-gate-web`, `ci-gate-security`, `gitleaks`, `semantic-pr-title`) and requires zero approving reviews. The planned CI file can be updated in PR 1; changing live GitHub protection/review settings requires an authorized owner to apply and verify the exact proposed contexts. No live setting has been changed by this implementation.

**Current-stage acceptance:** The local Stage 1 regression matrix passes, including broad shared-package/Proxy Go tests, integration-tag compilation, repo guards, docs lint, the gate/Helm/action-pin scripts, Actionlint, all web unit tests, TypeScript, MDX generation, and the production static build. The full external-service integration run is not claimed because its service dependencies were unavailable in this sandbox. A separate reviewer sweep and hosted required CI statuses must pass before merge. Subsequent PRs have not been started.

**Current PR 1 technical scope status:** Branch `fix/IBEX-895-pre-track-d-stage1-deny-by-default-assurance` was created from clean `main` at the baseline commit. `go test ./packages/... ./services/proxy/...` passes; `go test -tags=integration -run '^$' ./services/proxy` compiles the tagged suite without running service-dependent tests. `make repo-guards`, `make lint-docs`, `.github/scripts/test-ci-gate.sh`, `.github/scripts/check-required-ci-gates.sh`, `.github/scripts/test-proxy-helm-profile.sh`, `.github/scripts/validate-action-pins.sh`, Actionlint, all 177 web tests, TypeScript, Fumadocs MDX generation, and the full static build pass. The latest static search index is 4,847,258 bytes under its unchanged 5,000,000-byte cap. The build-time contract confirms ADR-0081 and the Phase 4 findings/risks summaries are indexed while the dense 4.P.0 page remains excluded. The missing roadmap documents were real Fumadocs walker omissions (`roadmapSource.getPages()` did not enumerate their records even though the routes were emitted); explicit compact fallback records now keep them searchable, the extraction script validates page artifacts and Orama's serialized document map, and the full pages remain directly accessible. The full external-service integration run, live branch-protection update, staging Redis Secret delivery/health, hosted CI, and final independent code review remain open gates.

**D1 entry is not guaranteed:** staging/API ingress, TLS, secrets, and a deployed authenticated console/API/SSE test environment are external dependencies and remain to be owned and proven.

**No conditional-acceptance bypass:** if the source tree/config manifests match the plan but the deployed or hosted environment does not, mark that gate blocked—not complete.
