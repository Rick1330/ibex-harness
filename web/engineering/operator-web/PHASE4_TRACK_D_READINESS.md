# IBEX Harness — Phase 4 Track D Readiness Review

**Repository:** `Rick1330/ibex-harness`
**Reviewed commit:** `8f8e130` (`chore(deps): bump alpine...`)
**Review date:** 2026-09-23

## Executive assessment

The repository is **not yet ready for full Track D implementation as a production operator product**, but it is ready to begin the **first controlled implementation slice after closing the remaining prerequisite contracts**. Phase 4 Track D is explicitly marked **planned for all six milestones**. The codebase currently contains a provisional operator connection shell and several backend/platform prerequisites, not the Track D capability slices themselves.

The appropriate next target is **4.D.1 — Authenticated Shell & Operational Overview**, but it must be built against the live operator topology and generated/typed API contracts. Do not start with the full Trace Inspector (4.D.2): its own milestone says the UI is blocked until specific 4.P.2 evidence joins and payload decisions are complete.

## What exists today

| Area | Current state | Readiness implication |
|---|---|---|
| Repository shape | Large Go/Python/TypeScript monorepo with API, proxy, context, memory, worker, dashboard, migrations, Helm, and evidence tooling | The required building blocks are distributed across services; implementation needs explicit contracts and cross-service fixtures. |
| Operator UI | `services/dashboard` is a static **4.P.0 topology/connection shell**. It supports API-origin allowlisting, provisional PAT login, session checks, logout, SSE connection state, reconnect behavior, and fail-closed API configuration. | Useful foundation, but not an Overview, navigation shell, org switcher, Explore, Incidents, Settings, or capability UI. |
| Operator API | Session routes, operator SSE, platform health, and an operator action ledger exist. The management API also has organizations/users/agents/tokens/providers/rate limits/usage query surfaces. | Authentication and health foundations exist; Track D read models and investigation endpoints do not. |
| Public web app | `web/src/app` is the public docs/benchmark/roadmap site, not the operator application. | Do not mistake docs-site roadmap or benchmark pages for Track D product evidence. |
| Evidence/data plane | 4.P.2 is in progress with correlation/checkpoint paths, outbox schemas, and persisted/deferred contract work. | Some D2 inputs exist, but the canonical read contract is not fully closed. |
| Privacy/governance | 4.P.3 is marked done, but safe-rendering/hostile-content testing is explicitly deferred to Track D. | Any content-bearing UI must include safe rendering and redaction tests. |
| Usage/cost | 4.P.4 is in progress; ledger, rate cards, budgets, hard-cap denial, and rollups exist, while reconciliation and saved-view work remain open. | D6 is not ready as a complete governance slice. |
| Production platform | 4.P.5 is in progress; restore-drill and CI supply-chain evidence exist, but staging Kyverno/PITR soak and chaos/load gates remain open. | Not a production rollout gate yet. |
| Assurance harness | 4.P.6 is planned; SDK/contract snapshots, four-role/two-tenant Playwright, and real dependency-path evidence are not complete. | This is the main blocker to calling D1 complete. |

## Track D milestone readiness

| Milestone | Roadmap status | Assessment |
|---|---|---|
| **4.D.1 Authenticated Shell & Operational Overview** | Planned | **Near-term candidate, but not ready for completion.** The current dashboard shell is only the connection contract. Need real operator origin, org/role context, Overview health/freshness, navigation, URL state, read-only data contracts, and four-role/two-tenant Playwright evidence. |
| **4.D.2 Explore & Provenance Trace Inspector** | Planned | **Blocked for full implementation.** Must close canonical request/trace joins, checkpoint IDs, AssemblyMetrics persistence, conversation/raw payload decision, composite-score payload versioning, directive snapshots, and expanded tool audit. A metadata-only degraded view is allowed only with explicit labels. |
| **4.D.3 Sessions, Memory, Context & Safe Replay Evidence** | Planned | **Blocked behind D2 and P.2/P.3 lifecycle contracts.** Requires governed session reconstruction, memory/context evidence, graph lineage, export/delete receipts, and sandboxed replay. |
| **4.D.4 Failures, Incidents & Evidence Bundles** | Planned | **Blocked behind D2, durable events, audit/evidence bundle contracts, and query platform.** No incident state machine/evidence-bundle product slice is present. |
| **4.D.5 Directives, Routing, Experiments & Controlled Actions** | Planned | **Later slice.** Requires step-up/dual approval, immutable directive/routing provenance, action ledger, staged rollout/abort evidence, and the Phase 4.5 drift contract. |
| **4.D.6 Usage, Cost Governance & Capacity** | Planned | **Later slice.** Backend billing foundations exist, but the UI, explainable policy decisions, reconciliation, hard-cap evidence in the operator journey, and capacity views are not complete. |

## Blocking prerequisite gaps

1. **4.P.0 is not closed.** The topology milestone still needs the topology ADR, environment-origin matrix, smoke transcript for login/API/SSE reconnect and drain, and docs-only rollback evidence.
2. **4.P.1 is not closed.** The roadmap marks it planned/partially landed. The action taxonomy, step-up rules, and two-tenant authorization matrix are still unchecked. The repository audit also identifies stale model-policy invalidation and other authorization/data consistency risks.
3. **4.P.2 is still in progress.** The golden evidence path is substantially present, but raw/conversation storage and retention remain unresolved. D2 explicitly lists the contract fields that must be settled before claiming an honest full Trace Inspector.
4. **4.P.6 is planned.** There is no complete generated-client/contract-snapshot pipeline or four-role/two-tenant operator Playwright gate. This directly prevents D1 completion.
5. **Track E is not a release gate yet.** Environment/fixtures, resilience/recovery, staged rollout, and Phase 4 sign-off remain downstream work; the repository should not label Track D production-ready before those gates.

## Verification performed

- Cloned the repository cleanly at commit `8f8e130`; working tree was clean before the review.
- Read the Phase 4 goals/tracks, all six Track D milestone specifications, Track P milestone checklists, operator architecture, and pre-Track-D audit notes.
- Confirmed all six Track D frontmatter statuses are `planned`.
- Ran `pnpm --dir services/dashboard test`: **14 tests passed**.
- Ran `pnpm --dir services/dashboard build`: **succeeded** and produced `services/dashboard/dist`.
- Attempted the API operator unit suite. The repository declares `pytest` under the API `dev` extra, but the current environment had not installed that extra, so the test command could not start (`pytest` executable/module unavailable). This is an environment setup gap, not evidence of passing or failing API tests.

## Recommended build sequence

### Gate 0 — close the contract prerequisites

Before adding product screens, finish a small prerequisite change set:

- Publish the operator API/OpenAPI read contracts for Overview, health/freshness, organizations, roles, and feature/route kill switches.
- Close the 4.P.0 topology ADR and smoke evidence.
- Record the 4.P.1 authorization matrix and step-up/action taxonomy, including negative cross-tenant cases.
- Decide and version the P.2 raw/conversation read model and retention semantics.
- Add the minimum P.6 contract snapshot and Playwright harness needed for D1.
- Install API dev dependencies and make the operator test command reproducible in CI.

### Gate 1 — build 4.D.1 vertically

Implement D1 end to end, in this order:

1. Generated/typed API client and stable DTOs.
2. Authenticated application shell in `services/dashboard` with org/role context.
3. Overview read model with health, freshness, partial/stale/degraded/error states.
4. URL-serializable org/time/filter state and safe deep links.
5. Read-only navigation entries for Explore, Incidents, Settings, and resources.
6. Route-level allowlist/kill switch and rollback behavior.
7. Four-role/two-tenant Playwright journeys, axe/keyboard checks, SSE reconnect/drain evidence, and performance budget.

### Gate 2 — only then start D2

Start the Trace Inspector after the P.2 checklist is closed or residual risk is explicitly accepted. Begin with a metadata-only, clearly degraded inspector if needed; do not expose raw prompt/tool content, inferred success, or non-joinable provenance as if it were authoritative.

## Bottom line

**We can continue, but the correct interpretation of “ready” is: ready to close the final Track P/D1 contracts and build 4.D.1—not ready to build all of Track D or to claim Phase 4 operator readiness.** The highest-value next implementation is the D1 vertical slice with contract-first tests, while keeping D2–D6 sequenced behind their stated evidence dependencies.
