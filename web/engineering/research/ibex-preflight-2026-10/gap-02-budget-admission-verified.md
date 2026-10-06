# GAP-02 — Budget and admission verification audit

**Repository:** `Rick1330/ibex-harness`<br>
**Audit target:** clean `main` at `7298e5ee7982b926630566c88830c99650c8eb37` (`7298e5e`)<br>
**Audit mode:** read-only; no repository files or implementation changed<br>
**Assigned gap identity:** GAP-02 / `budget-admission`<br>
**Canonical register identity:** `GAP-006` in `web/engineering/architecture-v2/18-gap-register.md`<br>
**Assessment:** **OPEN, P0** for atomic budget admission/reconciliation; current checks and usage projections are **shipped-local foundations**, not `shipped-accepted` hard-budget behavior.

## 1. Scope, snapshot, and method

I read the assigned memo, product strategy, implementation plan, and `SESSION_REPORT_2026-10-06.md`; inspected the current source, migrations, tests, architecture-v2 status/contracts, and merged PRs #934, #936, and #937. The repository checkout reports `main...origin/main`, no status output, and the exact target commit above.

The canonical authority is architecture-v2, not the historical strategy/audit. The memo's acceptance requirements (lines 102–113) were decomposed into six checks below. A classification describes **verified behavior at the target commit**, not the intent of a comment, PR title, or plan.

## 2. Strategy intent versus verified current state

The product strategy promises a self-hostable multi-tenant control/context plane with “hard tenant isolation” and **pre-call spend control** (`IBEX Harness_ Product Strategy, Gap Audit, and Recommended Redesign.md:7–19`). Its enforcement-plane description explicitly places budget reservation before provider selection/forwarding (`:43–53`), and its competitive differentiation calls for **atomic, fail-closed budget admission rather than post-call spend reporting** (`:103–122`).

The implementation plan correctly states that the local budget substrate is only partial: periods/rate cards, organization cached spend, estimates, post-response facts, and an asynchronous ClickHouse→PostgreSQL rollup exist, while atomic reservation, idempotency, settlement, and accepted evidence do not (`ibex-harness-implementation-plan.md:17–29`, especially the budget row at `:22`). It also places budget after G0, principal/tenant, idempotency/replay, and evidence dependencies (`:42–53`).

The verified implementation is narrower:

- `packages/billing/cache.go:66–84` (`Cache.Check`) reads a cached `BudgetSnapshot`, allows when remaining cents are positive, and increments no reserved/spent amount. `SnapshotForOrg` (`:87–95`) is cache/load only; `Invalidate` (`:176–189`) is local generation/cache invalidation, not a cross-process hold.
- `packages/billing/store.go:26–53` (`Store.LoadOrg`) uses a read-only PostgreSQL transaction. `loadActiveHardCap` (`:56–79`) selects `spent_cents_cached`; it has no conditional spend update, reservation insert, lock/hold, or settlement mutation.
- `services/proxy/internal/http/budget_middleware.go:23–26,32–66` checks after authentication and rate limiting. It denies an already exhausted snapshot but has no request-cost input and no reserve-before-provider operation.
- `services/proxy/internal/http/router_protected.go:85–95,127–150` conditionally constructs budget middleware only when `budgetCache != nil`, and orders the chat chain auth → agent verification → rate limit → budget → directive/parse/provider routing. This ordering is useful, but it does not create atomic admission. `services/proxy/internal/bootstrap/wire.go:388–397` and `bootstrap/billing.go:42–50` show that the cache itself is omitted when PostgreSQL is absent.
- `services/proxy/internal/http/chat_session_bridge.go:161–191` builds an estimated usage fact from **provider-reported** token counts after the call. It returns nil on estimate failure and cannot price the fallback version `"0"` produced by `resolvePublishedCard` (`:201–214`). It does not reserve input, max output, reasoning, retries, fallback attempts, tools, or other prospective spend.
- `services/proxy/internal/http/session/snapshot.go:144–185,192–220` schedules usage/evidence work post-response; evidence/usage-only work uses `TrySubmit` and logs a pool-full drop, while `EmitUsageFact` logs write errors rather than affecting the successful response.
- `packages/billing/factwriter.go:139–179,224–238` is a bounded asynchronous buffer. It reports drops and requeues failed batches, but its own comment notes `usage_facts` has no idempotency key and therefore avoids automatic retry after uncertain ClickHouse send outcomes. `infra/migrations/clickhouse/000005_usage_facts.up.sql:7–33` has `request_id` but no uniqueness constraint, reservation/attempt ID, or stable event identity.
- `services/worker/app/tasks/billing_reconcile.py:197–226,266–291` periodically sums estimated facts by org/period, updates `budget_periods.spent_cents_cached`, then publishes Redis invalidation after commit. This is an asynchronous projection refresh; no freshness/lag bound is defined in the inspected code. `reconcile_usage_actuals` (`:237–251`) returns `{status: deferred, reason: no_invoice_source}` pending issue #859.
- `infra/migrations/postgres/000038_billing.up.sql:54–69` defines budget periods and cached spend. `:75–97` defines `enforcement_decisions` as an allow/deny/unavailable audit table, but no reservation ledger or state machine. A bounded repository search found no application write path for that table; inserts appear in `infra/migrations/postgres/migrate_billing_integration_test.go` only.

The target commit therefore verifies a **hard-cap check against a possibly stale cached spend snapshot**, not a hard-budget guarantee.

## 3. Acceptance-criterion audit

### AC-1 — Concurrent near-cap admission never exceeds the cap

**Classification: OPEN.**

**Required check:** Run two or more independent proxy instances with a one-cent/one-unit remaining budget, stale hot-cache snapshots, concurrent cap/policy changes, and enough successful calls to prove aggregate reservations never exceed the cap.

**Current evidence:** `Cache.Check` (`packages/billing/cache.go:66–84`) only evaluates `rem` and returns; `Store.LoadOrg`/`loadActiveHardCap` (`packages/billing/store.go:26–79`) is read-only. There is no durable reservation ID, active-hold accounting, conditional update, serializable transaction, or cross-replica authority. Redis is used for invalidation (`bootstrap/billing.go:53–72`), not authorization/reservation. The expected race is therefore real: concurrent requests can all read the same positive remainder before asynchronous rollup.

**Tests:** `packages/billing/cache_test.go` (`TestCache_Check`, `TestCache_CheckAllowsWhenRemainingPositive`, `TestCache_LoaderErrorFailClosed`, `TestCache_LRUHitAndInvalidate`, `TestCache_EvictionKeepsGeneration`, `TestCache_LoadInvalidatedDuringLoad`) cover snapshot/cache semantics and loader errors, not concurrent reservations. `services/proxy/internal/http/budget_middleware_test.go` covers allowed/exhausted/unavailable single-request outcomes. No multi-instance, contention, or aggregate-reservation test exists.

**Intent versus proof:** The middleware comment says it “enforces org spend hard-caps,” and PR #934 improves its failure mapping, but neither supplies an atomic hold. The session report explicitly says durable reservation authority and concurrent hold invariants were not implemented (`SESSION_REPORT_2026-10-06.md:427–430`).

### AC-2 — Canonical decision/reservation/settlement events and no provider call on failure

**Classification: OPEN.**

**Required check:** Allow, deny, reservation, settle, release, and replay each produce exactly one tenant-scoped canonical event; a DB/outbox failure causes no provider invocation; crash/re-drive at every transition does not duplicate holds/debits/refunds.

**Current evidence:** `enforcement_decisions` is only a schema foundation (`000038_billing.up.sql:75–97`); no proxy/runtime application write was found. There is no reservation/settlement/release table or lifecycle. Usage evidence is post-response (`snapshot.go:144–220`), optional (`bootstrap/billing.go:77–104`), and fail-open with respect to the response. The provider route follows the check in `router_protected.go:127–150`, but no prospective reservation/outbox transaction gates it.

`packages/evidenceoutbox` has relay/store primitives and PR #936 adds evidence-relay hardening, but that is not proof that budget decisions are written, linked to a reservation, or durably acknowledged before provider work. The current ClickHouse usage writer also cannot serve as canonical admission authority.

**Tests/evidence:** No budget provider-spy/no-call-on-reservation-failure test, transition crash test, or exactly-once decision-event test exists. The hard-cap E2E (`web/e2e/hard-cap-denial.spec.ts:6–9,50–69`) uses an exhausted fixture/loader and asserts a denial response; it does not exercise real PostgreSQL, outbox, provider, or rollup behavior.

### AC-3 — Budget idempotency, replay, collision, and tenant isolation

**Classification: PARTIAL (generic boundary hardening only; budget acceptance remains open).**

**Required check:** Same tenant + same key + same body returns the same reservation/result; same key + different body conflicts; cross-tenant key/resource probing neither leaks nor mutates state; RLS, application org binding, Redis namespace, analytics queries, and anti-enumeration are proven.

**Current evidence:** PR #934 (`393c8b7`) adds generic idempotency-claim validation and tenant-scoped key construction in `packages/idempotency/store.go`, `packages/idempotency/redis.go`, and `services/proxy/internal/http/chat/idempotency.go`; its tests include invalid/missing tenant/key/fingerprint and response replay/header behavior. This is useful input validation and replay-boundary hardening.

It is **not a budget reservation idempotency contract**: no budget reservation ID/result is stored, no reservation state transition is replayed/settled exactly once, no body-bound budget ledger exists, and ClickHouse `request_id` is not unique (`000005_usage_facts.up.sql:7–33`). PostgreSQL RLS and composite org foreign keys provide tenant controls for existing tables (`000038_billing.up.sql:128–159`), but they do not create a budget hold ledger or prove cross-tenant budget replay behavior.

### AC-4 — Bounded prospective cost and explicit degraded/unknown outcomes

**Classification: PARTIAL.**

**Required check:** Unknown/stale price, tokenizer/capability mismatch, unavailable usage, max-output overrun, retry/fallback, partial stream, cancellation, provider timeout, and malformed usage must each have an explicit bounded cost and machine-readable result, with no provider work after denial.

**Current evidence:** `packages/billing/estimate.go:32–59` has defensive arithmetic/price matching and rejects negative/overflow operands. `buildFrozenUsageFact` (`chat_session_bridge.go:161–191`) computes an **after-the-fact estimate** from actual input/output usage. It is not a conservative pre-call bound and does not include requested max output, context, reasoning, retries, fallback attempts, tools, or provider capability constraints.

PR #934 does verify one important failure distinction: `BudgetMiddleware` now returns HTTP 503 / `SERVICE_DEGRADED` for nil cache, missing auth scope, nil org, or loader/cache error (`budget_middleware.go:21–25,35–60,75–78`), while true exhausted cap returns HTTP 402 / `BUDGET_EXCEEDED` (`:62–72`). Its tests are `TestBudgetMiddleware_nilCacheFailClosed503`, `TestBudgetMiddleware_loaderErrorFailClosed503`, `TestBudgetMiddleware_exhaustedReturns402`, `TestBudgetMiddleware_allowed`, and `TestBudgetMiddleware_authContextFailClosed`.

That is a **partial failure-contract correction**, not bounded admission: no pre-call price/fit/reservation path or complete provider/stream/fallback cost matrix is present. The router also omits the middleware entirely when `budgetCache` is nil (`router_protected.go:85–95`), although the direct middleware itself fails closed; whether supported runtime profiles can reach this omission remains a deployment/profile uncertainty.

### AC-5 — Projection, duplicate delivery, retry, outage, restart/restore, and deletion interactions do not alter canonical admission or multiply spend

**Classification: PARTIAL for the existing projection; OPEN for acceptance.**

**Required check:** Duplicate/out-of-order ClickHouse delivery, missed Redis invalidation, ClickHouse outage, worker retry/reprocessing, PostgreSQL restart/restore, and deletion/tombstone interactions must not change canonical admission or multiply billed facts.

**Current evidence:** `run_budget_spent_rollup` (`billing_reconcile.py:197–226`) scopes ClickHouse sums by org and period, updates PostgreSQL, and publishes Redis invalidation only after commit; the Celery task (`:254–264`) retries selected transport/ClickHouse/Redis failures with backoff/jitter. Worker tests in `services/worker/tests/unit/test_billing_reconcile.py` cover period scoping, zero spend, update/invalidation ordering, retry configuration, multiple periods, missing DSNs, and invalidation failures; the session memo records 22 tests passed for this file.

However, this projection is currently the **effective admission input** through `spent_cents_cached`, so stale/missed invalidation changes admission outcomes. ClickHouse facts have no uniqueness key and the writer documents uncertain-send/dedup limitations (`factwriter.go:224–238`; migration `000005...:7–33`). There is no authoritative reservation to remain stable while projections lag, no duplicate/out-of-order fact proof, and no restore/rebuild or deletion interaction acceptance. Provider invoice actual reconciliation is explicitly deferred (`billing_reconcile.py:237–251`, issue #859).

### AC-6 — Named-profile proof, recovery, operations, and measured performance

**Classification: OPEN.**

**Required check:** Record exact deployment profile, migrations/config/dependencies, recovery drill, operational alert/runbook, measured benchmark with concurrency/hardware/warm/cold/error policy/digests, owner/date, and review window in the status ledger.

**Current evidence:** `web/engineering/architecture-v2/18-gap-register.md` still records `GAP-006` as “Atomic reservation/idempotency/reconciliation is not accepted” with action “Define durable ledger and failure semantics.” The status/evidence and roadmap documents retain G0/G3/G4 gates and do not contain a shipped-accepted budget evidence packet. The session report says formal G0 acceptance, durable budget authority, and full recovery acceptance remain future work (`SESSION_REPORT_2026-10-06.md:414–430,447–473`). No measured admission p99/overspend bound or named-profile restore result was found.

The implementation plan's ≤20 ms discussion is a target, not a result. Component CI green status from PR #934 is not a hard-budget acceptance artifact.

## 4. Merged PR assessment

| PR | Merge commit / scope | GAP-02 effect | Verified conclusion |
|---|---|---|---|
| **#934** | `393c8b7d24787531e8b9c522b22b3b258c4d8cff`, merged 2026-10-06 05:54:11 UTC; principal/idempotency/fail-closed runtime controls | Changes `budget_middleware.go` and its tests so dependency/cache/auth-scope failures are 503 `SERVICE_DEGRADED`, while exhaustion remains 402 `BUDGET_EXCEEDED`; adds generic idempotency validation/replay hardening | **Partial positive change:** corrects one failure-semantic subgap and generic replay boundaries. It does not add reservation, prospective estimate, budget ledger, budget decision writes, settlement, or concurrency proof. The session report explicitly records that durable budget reservation authority was not implemented. |
| **#936** | `125fde3da214649f319cb54e5f87b96f2ed3575c`, merged 2026-10-06 10:06:21 UTC; memory validity/MCP limits/evidence relay changes | Touches `packages/evidenceoutbox` and related memory/MCP/docs paths, but no budget cache/store/middleware/rollup/reservation implementation | **No GAP-02 closure.** Evidence relay hardening may be a future dependency, but it does not link budget admission decisions to a durable outbox or prove before-ack evidence. |
| **#937** | `7298e5ee7982b926630566c88830c99650c8eb37`, merged 2026-10-06 15:05:06 UTC; web smoke/search-index limit sync | Only `.github` search-index smoke/deploy/CI files | **No GAP-02 effect.** It is the target main commit and does not change budget/admission behavior. |

The PR titles, comments, and session claims must not be read as completion claims. #934's budget-specific diff is limited to status-code/error-path semantics and tests; the durable ledger and lifecycle are absent at the audited commit.

## 5. Residual subgaps

1. **G0 contract freeze is not accepted:** tenant/resource scope, currency/unit, price/tokenizer provenance and freshness, estimate upper bound, unknown-price behavior, reservation TTL/recovery, overrun policy, failure status, evidence acknowledgement, retention, and rollout/rollback owner remain to be frozen.
2. **No authoritative reservation ledger:** need server-minted reservation ID, tenant-bound key/body hash, budget-period/resource reference, amount, state/version/lease/deadline, policy/pricing epoch, and immutable route/rate-card reference.
3. **No atomic cap enforcement:** must serialize settled spend plus active holds across independent proxy instances; Redis/cache may accelerate/invalidate but cannot authorize alone.
4. **No pre-call conservative bound:** must include input/context, max output/reasoning, retries/fallbacks, tools, capability/token fit, and immutable price source; deny/no-route before provider invocation when unknown or stale.
5. **No exactly-once budget lifecycle:** missing idempotent reserve, settle, release, adjustment/refund, attempt/fallback lineage, crash/retry handling, expiry, cancellation, timeout, malformed/partial usage, and overrun treatment.
6. **No durable decision/evidence linkage:** `enforcement_decisions` is schema-only at runtime; no atomic state + outbox evidence before the response claims durable admission.
7. **Projection/dedup gap:** usage facts lack uniqueness/idempotency identity; ClickHouse uncertain sends, retries, duplicate/out-of-order delivery, rollup lag, and restore/rebuild can affect the effective cached spend.
8. **Actual-cost reconciliation is deferred:** `reconcile_usage_actuals` is a declared no-op pending #859; estimated spend must not be represented as provider invoice actuals.
9. **Degraded-profile semantics need runtime proof:** direct middleware fails closed, but router construction omits it when cache is nil; supported profile gates and production behavior are unknown.
10. **Budget scope is only organization hard cap:** project/API-key/agent/user/service/run/session/hierarchical limits are absent and need an explicit product-scope decision rather than accidental expansion.
11. **No profile-specific performance/recovery acceptance:** no named HA/deployment profile, concurrency/hardware benchmark, overspend bound, RPO/RTO, restore drill, alert/runbook, or owner/date/review window proves the guarantee.

## 6. Dependencies and shared boundary ownership

- **G0 / architecture + product/finance/SRE:** freeze authority, units, scope, price freshness, hard-cap versus alert-only meaning, failure/error contract, retention, and acceptance profile before new budget schema/lifecycle work (`architecture-v2/17-roadmap-and-gates.md`; `18-gap-register.md`).
- **G1 identity/principal/tenant (Auth/Proxy + Context):** bind verified principal/org/agent/resource/run context to reservation and evidence; preserve auth → agent → rate → budget ordering; enforce RLS/application org binding and anti-enumeration.
- **G2 idempotency/replay (Proxy/platform):** canonical request/body hash, key scope/collision semantics, response replay, TTL/crash/re-drive, and safe settle/release retries are prerequisites to budget transitions. PR #934 provides generic validation but not the budget ledger.
- **G3 budget/provider (Proxy/Billing/Provider):** proxy owns no-provider-after-deny and request-bound admission; billing owns authoritative PostgreSQL ledger/transaction; provider routing must expose immutable deployment/capability/price/residency facts and attempt lineage.
- **G4 evidence/outbox (Evidence/Security/Platform):** decide which admission/deny/reserve/settle/release events are acknowledgement-required, write canonical state + outbox atomically, relay/deduplicate/replay with redaction and retention. PR #936 improves relay mechanics but does not wire budget decisions.
- **Analytics/worker (Worker/Data):** ClickHouse is a tenant-filtered projection only; worker rollup and Redis invalidation must never be authoritative or able to authorize. Define lag/freshness, duplicate handling, backfill/rebuild, and outage behavior.
- **G8 operations/recovery (Platform/SRE):** named deployment profile, backup/restore, migration/rollback, restart/lease recovery, alerting/runbook, RPO/RTO, and measured latency/overspend evidence.
- **Provider/invoice owner:** actual invoice source and reconciliation remain external/deferred under issue #859; settlement must distinguish estimated usage from invoice actuals.

## 7. Exact acceptance checks required before `shipped-accepted`

1. **Contention:** two or more independent proxy instances, near-cap remainder, warm/stale caches, concurrent budget updates; assert committed reservations plus settled spend never exceed the cap, with no provider call after a denied reservation.
2. **Atomic lifecycle:** force DB/outbox failure at allow/deny/reserve/settle/release and crash between every transition; re-drive lost responses; assert one canonical tenant-scoped event and no duplicate hold/debit/refund.
3. **Replay/collision:** same tenant/key/body returns the same reservation/result; same key/different body is a typed conflict; cross-tenant/resource reuse cannot read or mutate another tenant. Verify RLS, app `org_id`, Redis namespace, analytics predicate, and anti-enumeration.
4. **Bounded estimate:** test unknown/stale prices, tokenizer/capability mismatch, missing usage, max-output/reasoning, retries/fallbacks/tools, partial streaming, cancellation, timeout, malformed usage, and overrun; assert machine-readable outcome and bounded accounting.
5. **Projection resilience:** duplicate/out-of-order ClickHouse facts, uncertain send, worker retry/reprocessing, delayed/missed Redis invalidation, ClickHouse outage, PostgreSQL restart/restore, and deletion/tombstone interactions must not alter canonical admission or multiply billed effects.
6. **Profile proof:** publish exact profile/config/migrations/dependency digests, owner/date/review expiry, alert/runbook, recovery/restore/RPO/RTO artifact, and measured benchmark (concurrency, hardware, warm/cold, error policy, p99 and overspend bound). Record it in the canonical status ledger.
7. **Provider ordering:** provider spy tests must prove no provider invocation after unknown authority, failed outbox, denied reservation, stale price, or token-fit failure; test auth → agent → rate → budget order and fallback reservation/attempt lineage.
8. **Actuals distinction:** keep invoice actual reconciliation explicitly deferred until #859 or an equivalent authoritative source; never use `actual_cost_cents` to imply provider invoice truth without source evidence.

## 8. Risks and uncertainties

- The audit is bounded to the checkout and repository search; it cannot disprove an unindexed/private deployment mechanism outside the repository.
- Production/staging/HA profile activation, PostgreSQL/ClickHouse/Redis availability, rollup interval/lag, and cache omission behavior are not established by local source inspection.
- Provider usage completeness for streaming, reasoning, cached input, tools, retries, and fallbacks is unknown; the current post-response fact path should not be treated as a complete cost source.
- The Go test suites were not re-executed during this audit because `go` is unavailable in the sandbox. Source/tests were inspected directly. The session report records prior Go/race/hosted green gates for PR #934, but those are historical component validation and do not satisfy the missing budget acceptance checks.
- Existing unit/E2E tests can pass while the atomic guarantee is absent: they exercise a single snapshot/denial fixture, arithmetic, or rollup mocks rather than multi-replica contention and crash/replay semantics.
- `enforcement_decisions` has RLS/composite org protections and integration migration tests, but that is schema/tenant evidence, not proof of runtime decision recording.
- A future budget ledger must coordinate with provider capability/price manifests and evidence acknowledgement; implementing it in isolation risks accepting a reservation that cannot be priced, routed, evidenced, or recovered.

## Final disposition

**Keep GAP-02/GAP-006 OPEN at P0.** Mark the organization budget period/rate-card store, local cached hard-cap check, corrected 503-versus-402 failure mapping, estimated usage fact writer, and asynchronous rollup as **shipped-local/partial foundations**. Do not claim atomic hard-budget enforcement, exactly-once reconciliation, or `shipped-accepted` evidence until G0 is formally accepted and the ledger, pre-call bound/reservation, idempotent lifecycle, evidence coupling, projection resilience, and named-profile proof above are demonstrated.
