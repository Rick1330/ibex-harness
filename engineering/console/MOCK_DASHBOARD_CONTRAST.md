# Mock Dashboard Review and Main-Repository Contrast

**Mock source:** `dash-board-mock.zip`
**Main repository:** `Rick1330/ibex-harness` at `8f8e130`
**Review date:** 2026-09-23

## Executive assessment

The mock dashboard is a strong **product and UX reference implementation**. It is materially ahead of the main repository’s current operator UI and covers nearly the complete Track D information architecture. It should become the visual and interaction baseline for the build.

It is not yet a production integration: the mock is a Next.js application whose domain APIs and records are primarily fixture-backed or browser-local. The main repository has the security, tenancy, management, evidence, billing, and platform foundations, but it does not yet expose the read-model contracts needed to power most of the mock pages.

The best path is therefore **not to replace the mock with the current static dashboard shell** and not to wire fixtures directly into production. Instead:

1. Preserve the mock as the product reference and convert its domain types into versioned API DTOs.
2. Build 4.D.1 first against the real operator session/topology contracts.
3. Add read APIs and evidence contracts in the main repository one vertical slice at a time.
4. Replace each fixture adapter with a real client only after its backend contract and tenant/security tests exist.

## What the mock contains

The mock has a complete Next.js App Router surface with these routes:

| Product area | Mock routes |
|---|---|
| Authentication | `/login`, `/signup`, `/enroll-totp` |
| Shell / overview | `/dashboard` |
| Agents | `/dashboard/agents`, `/dashboard/agents/[agentId]` |
| Explore and traces | `/dashboard/explore`, `/dashboard/explore/t/[traceId]` |
| Sessions and memories | `/dashboard/sessions`, `/dashboard/sessions/[sessionId]`, `/dashboard/memories`, `/dashboard/memories/[memoryId]` |
| Incidents | `/dashboard/incidents`, `/dashboard/incidents/[incidentId]` |
| Directives | `/dashboard/directives`, `/dashboard/directives/[directiveId]` |
| Drift | `/dashboard/drift`, `/dashboard/drift/[alertId]` |
| Analytics and billing | `/dashboard/analytics`, `/dashboard/billing` |
| Settings | `/dashboard/settings` |

It also includes domain components and types for Explore, Trace Inspector, sessions, replay, incidents, directives, drift, analytics, billing, agents, auth, onboarding, settings, providers, tokens, webhooks, audit, legal holds, and deletion receipts.

## Strong product decisions in the mock

### 1. The information architecture matches the intended Track D product

The mock does not treat the dashboard as a generic chart page. Its primary navigation supports the intended investigation loop:

> Overview → Explore → Trace/session evidence → Incidents → Controlled policy/action surfaces → Usage and governance.

This aligns well with the roadmap’s sequencing of D1 through D6 and is significantly closer to the intended product than the current repository dashboard shell.

### 2. Global context is treated as a first-class interaction

The mock includes an organization/environment switcher, global time range control, shell health/freshness state, pinned/recent resources, breadcrumbs, and preserved query context. This directly supports the D1 requirements for organization context, global search/explore entry, freshness, and URL state.

The `ShellHealth` model is especially useful as a design contract:

- `freshness`: live, historical, reconnecting, degraded, partial, stale
- `connection`: ready, draining, reconnecting, unreachable
- `last_successful_sync`
- `lag_ms`
- human-readable detail

The main repository has `/ready`, platform health, and operator SSE foundations, but it does not yet have this consolidated shell-level read model.

### 3. The mock has unusually good “honesty” behavior

The design rationale documents consistently distinguish:

- estimated cost from actual ledger cost;
- partial data from empty data;
- unavailable from denied;
- metadata-only from content-bearing evidence;
- fixture behavior from real API behavior;
- permissions from feature flags, kill switches, tier limits, and step-up state;
- a missing baseline from a missing feature.

This is exactly the right direction for the repository’s Track D requirements, especially D2, D4, D5, and D6. These labels should be retained when the mock is connected to real data.

### 4. Trace Inspector is aligned with the roadmap’s differentiated product wedge

The mock’s Trace Inspector is organized around the intended three-layer model:

1. summary/provenance strip;
2. candidate matrix with inclusion/exclusion reasoning;
3. explain tree / score contribution breakdown.

It also contains timeline/flame views, directive links, tool events, replay status, redacted JSON, and pivots. This is much closer to the roadmap’s required provenance debugger than a generic APM trace detail page.

The important caveat is that the main repository’s 4.P.2 contract is not fully closed, so the mock must not be treated as proof that the underlying evidence joins already exist.

### 5. Governance surfaces are modeled as controlled workflows, not decorative buttons

Settings, directives, incidents, replay, privacy, and action-ledger surfaces include step-up, dual approval, permission gates, feature flags, kill switches, deletion receipts, audit outcomes, and rollback-oriented copy. This is a strong translation of the security requirements into product behavior.

## Mock-to-repository contrast

| Capability | Mock dashboard | Main repository | Assessment |
|---|---|---|---|
| Authenticated shell | Full login/signup/TOTP routes and auth provider | Provisional PAT login/session cookie/SSE shell in `services/dashboard`; backend operator session routes exist | Mock is ahead in UX; repository is the authority for real auth and session wiring. |
| Organization context | Org/environment switcher and context-aware shell | Organizations and tenant-scoped management APIs exist; shell-level org switching contract is not complete | Good candidate for D1 contract work. |
| Health/freshness | Consolidated `ShellHealth` model and visible state language | `/ready`, platform health, drain, and SSE primitives exist | Merge mock’s UX model with repository’s real probes. |
| Overview | Product dashboard with KPIs, trend charts, partial-data states, onboarding | No Track D overview endpoint or operator page | D1 backend read model is missing. |
| Explore | Query bar, facets, saved-view intent, results, pivots | Usage query exists; no general trace/session/failure Explore API | D2 read API and query grammar are missing. |
| Trace Inspector | Summary, candidate matrix, explain tree, flame graph, evidence badges, replay links | Evidence persistence is partial; P.2 still has open raw/conversation and retention decisions | Do not wire fully until P.2 joins are versioned. |
| Sessions / memory | Session timeline, memory details, replay sandbox, governed controls | Sessions/checkpoints/memory services exist, but no operator read API assembled for this UI | D3 can reuse real data primitives after a read projection is defined. |
| Incidents | Incident lifecycle, assignment, timeline, bundle-oriented detail | No Track D incident projection/state-machine API found | D4 backend is missing. |
| Directives / actions | Versioning, promotion console, approval and rollback affordances | Model policies/provider/routing foundations exist; no complete D5 operator workflow API | D5 must be built around immutable versions and action ledger. |
| Drift | Baseline/alert views and Phase 4.5-aware language | Drift is not a completed Phase 4 contract; roadmap gates UI behind Phase 4.5 producer contract | Keep mock route behind a feature flag until contract exists. |
| Analytics / billing | Spend-first billing, burn-down, budget/enforcement language, analytics fixtures | Billing schema, usage ledger, rate cards, budgets, hard-cap middleware, and rollups exist; reconciliation remains open | Strong D6 visual target; wire only to reconciled facts and explicit completeness labels. |
| Settings | Tokens, providers, webhooks, audit, legal hold, deletion, security tabs | Real token/provider/org/user/rate-limit/privacy/legal-hold APIs exist | Best near-term area for contract mapping after D1. |
| Onboarding | Checklist with agent → PAT → test request → invite/budget | Agent and token APIs exist; no complete onboarding read/write contract | Useful D1/D6 enhancement, but localStorage must be replaced or bounded by server state. |
| Accessibility/responsiveness | Responsive sidebar, keyboard-oriented controls, reduced-motion handling, state labels | Main repo has no equivalent operator product surface | Preserve and add axe/keyboard evidence in P.6/E.1. |

## Important implementation reality: fixture-backed versus real

The mock’s architecture is intentionally useful but must be read correctly:

- The build has **18 routes and succeeds**, proving the product surface is coherent as a front end.
- Many domain APIs return generated fixtures, delayed promises, or local state rather than calling the main repository.
- Onboarding progress is persisted under browser `localStorage`.
- Settings interactions simulate API errors and authorization gates in client code.
- Analytics, billing, Explore, sessions, incidents, directives, and drift use fixture datasets and typed models.
- Some design rationales explicitly document that a read endpoint is not yet available, which is good honesty but also confirms the integration work remains.

The mock should therefore be treated as a **contract discovery artifact and visual acceptance target**, not as a drop-in production dashboard.

## Contract mismatches to resolve before wiring

### Organization and URL state

The mock assumes organization/environment state can be globally selected and persisted in URLs. The main repository requires explicit server-side `org_id` scoping in every data query. Define a shared `OperatorContext` contract containing:

- authenticated principal;
- active organization;
- role and permission bitmap;
- step-up status and expiry;
- feature flags and kill switches;
- time range, filters, and freshness state.

### Trace and evidence identity

The mock expects easy pivots among `trace_id`, `span_id`, `request_id`, `session_id`, and checkpoint/memory IDs. The main repository’s P.2 checklist explicitly identifies these joins as work in progress. These IDs need a stable versioned DTO and cross-tenant `404`/empty-search behavior before D2 is made authoritative.

### Data completeness and retention

The mock’s UI is prepared for partial and stale data, but the backend must provide explicit `completeness`, `freshness`, `sampling`, and `retention` fields. Never infer “no data” from a missing ClickHouse bucket or absent optional evidence.

### Controlled actions

The mock’s D5 settings and directive flows imply real preview, approval, step-up, idempotency, action ledger, and rollback behavior. The main repository has an operator ledger and authorization gates, but the end-to-end controlled-action contract is not complete. The UI should remain read-only or fixture-backed until those API states exist.

### Billing and cost

The mock correctly labels estimated cost as advisory and reserves actual cost for governance. The main repository has the billing schema and hard-cap path, but estimate-to-actual reconciliation is explicitly deferred. D6 should ship with visible completeness/version labels and should not present estimate data as final spend.

### Drift

The mock includes drift pages, but the roadmap explicitly says drift UI should be gated behind the Phase 4.5 fingerprint producer contract. Keep this screen disabled or clearly experimental in the first real integration.

## Build recommendation

### Phase 1 — adopt the mock as the D1 product baseline

Do not rebuild the visual language from scratch. Extract and preserve:

- shell layout and navigation hierarchy;
- org/environment switcher;
- global time-range control;
- shell health/freshness presentation;
- empty/error/partial/stale/degraded state components;
- onboarding checklist behavior;
- responsive and keyboard behavior;
- typography, restrained motion, and dark/light themes.

Move the implementation into the repository’s intended operator application location, or replace `services/dashboard` with the Next.js shell only after deciding the deployment topology. Do not mix two independent dashboard implementations indefinitely.

### Phase 2 — define real D1 contracts

Add a versioned API contract for:

- `GET /v1/operator/context`;
- `GET /v1/operator/overview`;
- `GET /v1/operator/platform/health` integration with shell health;
- organization/environment selection;
- route/feature availability;
- freshness and completeness metadata;
- read-only navigation capability flags.

Then replace the mock auth provider and shell fixture with the repository’s session cookies, CSRF protection, SSE, tenant authorization, and route kill switch.

### Phase 3 — connect settings before deep investigation

The mock settings pages are closest to existing repository APIs. Use them to validate real API client conventions for tokens, providers, organizations, users, privacy, legal holds, and audit/action outcomes. This provides an early end-to-end test of permissions and tenant isolation without prematurely exposing raw trace content.

### Phase 4 — build D2 from evidence contracts

Use the mock Trace Inspector as the acceptance target, but implement it in stages:

1. metadata-only summary and list;
2. joinable provenance IDs and completeness badges;
3. candidate matrix and exclusions;
4. composite score explanation;
5. redacted conversation/tool payloads;
6. replay and bidirectional pivots.

Each stage should be gated by the corresponding P.2 evidence fixture and cross-tenant test.

## Verification of the mock

- `npm ci --no-audit --no-fund`: succeeded.
- `npm run build`: succeeded; all 18 application routes compiled and generated.
- `npm run lint`: failed with **19 errors and 6 warnings**, primarily React hook set-state-in-effect rules, an impure `Math.random()` call in the sidebar skeleton, and unused variables.

The lint failures do not invalidate the design, but they should be cleaned up before using the mock as the production front end. In particular, fix the impure render-time randomness and the effect-driven initialization patterns before adding live data fetching.

## Bottom line

The mock is the strongest current representation of what Track D should become. The main repository is the stronger source of truth for security, tenancy, evidence durability, billing enforcement, and deployment. The next build should combine them:

> **Mock for product behavior and visual acceptance; main repo for contracts, authorization, evidence, persistence, and operational truth.**

The immediate implementation target remains **4.D.1**, using the mock’s shell and Overview design while closing the 4.P.0/4.P.1/4.P.6 contracts. Full Trace Inspector, replay, incidents, controlled actions, drift, and cost governance should follow their roadmap dependencies rather than being connected directly to fixture-shaped data.
