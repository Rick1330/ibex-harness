# Console D1 local readiness

This source slice preserves the existing Console navigation, typography, card surfaces, and spacing. It replaces only the Overview's data state and suppresses fixture identity/counts when `liveMode` is active. It is **not a production deployment approval** and does not close the hosted identity, topology, accessibility, visual, performance, or operator-E2E evidence gates in the Phase 4 roadmap.

## Explicit modes

- Default/build/production without the live opt-in: dashboard is unavailable; no mock fixture is rendered.
- Non-production preview: set `CONSOLE_DATA_MODE=preview`, `CONSOLE_PREVIEW=1`, and `NEXT_PUBLIC_CONSOLE_PREVIEW=1`. This is deterministic mock data and is labeled as preview in the shared shell.
- Read-only D1 integration: set `CONSOLE_DATA_MODE=live`, `CONSOLE_READ_ONLY=1`, and server-only `IBEX_OPERATOR_API_ORIGIN=https://<trusted-api-origin>`. Set `IBEX_OPERATOR_SESSION_COOKIE_NAME` only if the API session cookie name differs from `ibex_session`. Never set the API origin as `NEXT_PUBLIC_*`. The Console forwards only the access-session cookie; refresh/CSRF cookies and arbitrary browser headers are not forwarded. The API still validates the session, feature state, metadata-read grant, and organization scope on every request.

## Mounted read contracts

- `GET /v1/operator/context`: verified organization identity and database-verified role (nullable if there is no matching local user). Session identifiers, subjects, permission bitmaps, and credentials are not serialized to the browser.
- `GET /v1/operator/overview`: organization name/status and active user/agent counts from one bounded tenant-scoped query.
- `GET /v1/operator/platform/health`: existing dependency-health endpoint.
- `GET /v1/operator/events/stream`: existing metadata-permission-protected SSE, proxied same-origin at `/api/operator/events/stream`; the browser's native `EventSource` owns automatic Last-Event-ID reconnect. D1 displays connection state only and neither stores nor renders event payloads.

No activity feed, requests, tokens, sessions, cost, latency, model shares, per-agent rank, data freshness, login/PAT exchange, refresh/logout, writes, or production identity mapping is claimed by this slice. The page displays those measures as unavailable instead of substituting fixtures. The current access-cookie issuer/rotation policy, identity role mapping, P0 Pages-vs-server-capable runtime choice, hosted e2e/rollback proof, and external D0/P6 attestations remain hard gates; do not enable hosted live mode before their owners close them.

## Automated evidence in this source slice

- `pnpm --filter @ibex/console test:e2e` exercises the preserved preview shell, nested deferred-route rewrite, desktop/mobile navigation, keyboard focus, horizontal-overflow, and axe WCAG 2.2 AA checks.
- `pnpm --filter @ibex/console test:e2e:live` runs a loopback HTTPS fixture API and the real Console server path. It validates context/Overview/health parsing, live tenant rendering, no fixture identity substitution, access-cookie-only forwarding, and the same-origin SSE proxy/connected state. It does not contact a hosted API or prove real identity, tenants, CSRF/session lifecycle, proxy buffering, production SSE reconnect/drain, or rollout/rollback.
- CI retains Playwright traces and failure artifacts for 14 days. OpenAPI and mounted-route inventory snapshots are checked for freshness.

## Local verification record — 2026-09-26

- API: **742 unit tests passed**; **11 PostgreSQL integration tests passed**, including a new D1 RLS test with two tenants, active/invited/deleted users, active/paused/deleted agents, correct tenant counts, and anti-enumerating wrong-tenant denial. This ran against a disposable local PostgreSQL 16/pgvector database with repository migrations applied.
- Console: ESLint, TypeScript, Vitest (**17 tests**), and the production build passed. The preview/deferred browser suite passed **3 tests**, including keyboard focus, responsive overflow/navigation, desktop/mobile axe WCAG 2.2 AA audits, and a deferred-route no-fixture assertion. The live browser journey passed **1 test**, including live DTO rendering, access-cookie-only upstream forwarding, same-origin SSE resume, no fixture substitution, and WCAG 2.2 AA.
- OpenAPI snapshot and generated route inventory are fresh. Ruff passed for changed API code/tests.

These are local source/runtime checks. The live browser uses a loopback fixture API; the PostgreSQL stack is local and disposable. Neither validates the deployed AuthService, approved staging origins/runtime, real user/session lifecycle, all four roles across two real tenants, production SSE edge behavior, rollback, or P6 per-slice certification. **4.D.1 remains unaccepted until its external entry and exit gates are evidenced.**
