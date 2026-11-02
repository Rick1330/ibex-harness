# IBEX Console (`@ibex/console`)

`services/console` is the canonical operator application. It is a Nuxt 4 server-rendered app with a server-only operator BFF. The dashboard compatibility shell was retired by ADR-0090.

The Console is the operations plane for the memory/context lifecycle (ADR-0089): agents, sessions, memories, evidence, directives, policies, trace exploration, platform health, and settings. Incidents, drift, analytics, budgets, providers, MCP tools, and access are a separate **platform tier** and are not part of the default navigation.

Live surfaces render only evidence returned by the operator API. Preview surfaces are labelled blueprints and may render illustrative fixtures under the conditions in [ADR-0089 §4](../../engineering/adr/0089-product-shape-and-console-scope.md). A live surface never falls back to fixtures.

`Live` describes the read path, not acceptance. Every live Console row remains provisional in the status ledger; preview rows remain deferred until an owning contract exists, and platform-tier rows also need a named design partner.

## Local commands

From the repository root:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
pnpm --filter @ibex/console test
pnpm --filter @ibex/console lint
pnpm --filter @ibex/console typecheck
pnpm --filter @ibex/console build
pnpm --filter @ibex/console test:e2e
pnpm --filter @ibex/console test:e2e:live
```

Open `/`. To exercise live D1/D2 against a local operator API:

```bash
IBEX_OPERATOR_API_ORIGIN=https://operator.example.invalid \
IBEX_OPERATOR_SESSION_COOKIE_NAME=ibex_session \
pnpm --filter @ibex/console dev
```

The API origin must be HTTPS whenever an operator session cookie is present. The BFF forwards only the configured access cookie; refresh, CSRF, and unrelated cookies are never forwarded.

## Surface status

`shared/operator/surfaces.ts` is the machine-readable source of truth. This table is derived from it and checked by `pnpm --filter @ibex/console check:surfaces`.

### Core tier — the memory/context lifecycle

| Surface | Route | Status | Evidence and boundary |
| --- | --- | --- | --- |
| Overview | `/` | Live D1 | Tenant-scoped organization snapshot; no fixture fallback. |
| Agents | `/agents` | Live D2 | Tenant-scoped inventory and detail from `operator.agents.v1`; no fixture fallback. |
| Sessions | `/sessions` | Preview | Session timeline and inspector; no session read model or turn-to-trace join is connected. |
| Memories | `/memories` | Live D2 | Metadata-only index from `operator.memories.v1`; content is not exposed. |
| Evidence | `/evidence` | Preview | Certification coverage, tombstones, and relay chain; no summary contract is connected. |
| Directives | `/directives` | Preview (deferred) | Version timeline and diff; no owning API router exists. |
| Policies | `/policies` | Preview | Snapshots, readable rules, and diffs; run-to-policy provenance is not connected. |
| Explore | `/explore`, `/explore/t/:traceId`, `/explore/r/:runId` | Live D2 | Metadata-only trace list, multi-run trace view, and validated run detail using `operator.trace-query.v1`. |
| Platform | `/platform` | Live D1 | Dependency health, ingestion lag, retention, backup, restore, and deployment evidence. |
| Settings | `/settings` | Preview | Illustrative configuration only; no write path, owner attestation, or audit link is connected. |

### Platform tier — hidden from default navigation

| Surface | Route | Status | Evidence and boundary |
| --- | --- | --- | --- |
| Incidents | `/incidents` | Preview | Incident response design; no incident contract is connected. |
| Drift | `/drift` | Preview | Drift inbox and baselines; no drift contract is connected. |
| Audit log | `/audit` | Preview | Audit events and integrity; no append-only audit contract is connected. |
| Budgets | `/budgets` | Preview | Reservation design; no certified accounting watermark is connected. |
| Analytics | `/analytics` | Preview | Usage analytics design; ClickHouse projections are not connected. |
| Providers | `/providers` | Preview | Provider manifests and model capabilities; no operator projection is connected. |
| MCP tools | `/mcp-tools` | Preview | Tool inventory and schemas; invocation auditing is not connected. |
| Access | `/access` | Preview | Members, keys, and roles; AuthService login, MFA, and revocation are not connected. |

`/dashboard` and nested legacy paths return permanent redirects to the approved top-level routes. Unknown legacy paths return `404`.

## Preview policy

Preview fixtures are allowed only under [ADR-0089 §4](../../engineering/adr/0089-product-shape-and-console-scope.md):

- the surface is statically `preview` and renders a persistent `Illustrative preview` banner;
- the page verdict states coverage, for example `0% live · illustrative only`;
- fixture tenant identifiers use the reserved `org_demo_` prefix;
- fixture modules live in `app/lib/*-preview.ts` and are registered in one enumerable registry;
- no live data path imports a fixture module;
- fixtures never contain credentials, tokens, real personal data, or anything that could be mistaken for a secret.

Development demo mode (`CONSOLE_DEMO_ENABLED`) is compile-time `import.meta.dev` only. It renders the `Illustrative` chip, never activates in a production build, and is not a data mode.

## BFF boundary

Browser code calls same-origin Nuxt server routes only:

- `GET /api/operator/context`
- `GET /api/operator/overview`
- `GET /api/operator/platform/health`
- `GET /api/operator/traces`
- `GET /api/operator/traces/:traceId`
- `GET /api/operator/traces/runs/:runId`
- `GET /api/operator/events/stream`

The BFF strips `org_id` before returning D1 context and overview payloads. Responses use runtime Zod validation, `Cache-Control: private, no-store`, `Vary: Cookie`, and same-origin SSE restrictions.

## Configuration boundary

| Variable | Meaning |
| --- | --- |
| `IBEX_OPERATOR_API_ORIGIN` | Server-only approved upstream origin for operator reads. |
| `IBEX_OPERATOR_SESSION_COOKIE_NAME` | Access-session cookie name; defaults to `ibex_session`. |
| `NUXT_PUBLIC_IBEX_ENV` | Environment label shown in the console chrome. |

The Console exposes no mutation routes. Read-only behavior is structural, not flag-gated (ADR-0091): `CONSOLE_READ_ONLY` is reserved and is not consulted by the Nuxt implementation. There is no production preview-data mode; the only fixture substitution is compile-time `import.meta.dev`. No bearer token is available to browser configuration, and the client holds no organization ID authority.

## Verification

- `pnpm --filter @ibex/console test` covers contracts, query parsing, return-target safety, and surface status.
- `pnpm --filter @ibex/console test:e2e` verifies fail-closed production behavior, legacy redirects, preview labelling, mobile navigation, and WCAG 2.2 AA checks.
- `pnpm --filter @ibex/console test:e2e:live` runs a loopback HTTPS fixture API and the real Nuxt server path. It verifies D1/D2 rendering, access-cookie-only forwarding, SSE resume, hostile-event non-retention, and axe coverage.

Any expansion beyond the current live slice must add an owning API contract, tenant-negative tests, redaction/hostile-content tests, accessibility checks, performance evidence, and a rollback plan before changing this README's status.
