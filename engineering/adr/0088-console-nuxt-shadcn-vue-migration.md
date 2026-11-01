---
title: "ADR-0088: Console migration to Nuxt 4 + shadcn-vue"
description: "Architecture decision record 0088: rebuild the canonical operator Console on Nuxt 4, Vue 3, Tailwind v4, and shadcn-vue with a same-origin Nitro BFF, explicit live/preview status, and no fabricated tenant data."
adrId: "0088"
status: "Accepted"
date: "2026-10-25"
authors: "IBEX Harness team"
---

::decision-banner{status="Accepted" date="2026-10-25" id="0088"}
::

> **Amended 2026-11-01 by [ADR-0089](0089-product-shape-and-console-scope.md) §4.** The live/preview boundary in §3 and the fixture-removal requirement in §5 are replaced. Preview surfaces may render clearly labelled illustrative fixtures under the conditions in ADR-0089 §4. The prohibition on fixtures in live surfaces is unchanged. The Nuxt/Nitro stack decision in §1–§2 is unchanged.

# ADR-0088: Console migration to Nuxt 4 + shadcn-vue

- **Status:** Accepted
- **Date:** 2026-10-25
- **Authors:** IBEX Harness team
- **Supersedes:** [ADR-0078](0078-operator-runtime-topology.md) for the Console runtime topology; [ADR-0080](0080-ibex-console-service-rename.md) only for its Next.js implementation detail.

## Context

`services/console` is the canonical operator application, but its Next.js 16 / React 19 implementation no longer matches the product's presentation needs or the repository's public-site visual system. The public site uses Nuxt 4, Vue 3, Tailwind v4, and a restrained Geist/paper/graphite/lime visual language under `site/`.

The existing Console also contains broad preview fixtures and mutating UI for surfaces without owning contracts. That is useful as a product sketch, but it makes it easy to mistake presentation for evidence. The current product requirement is narrower and stricter:

- Rebuild the Console on the same framework family as `site/`.
- Use shadcn-vue and the `dashboard-01` block as the starting shell.
- Keep a server-only BFF; the browser must never receive upstream credentials or tenant authority.
- Mount only D1 and D2 reads as live surfaces.
- Render D3+ surfaces as clearly labeled preview designs with **no fabricated data**.
- Match the site's visual language rather than copying Langfuse or the previous mock.

ADR-0078 locked a static SPA on Cloudflare Pages with no BFF. The existing Next.js Console already contradicts that assumption through server-side reads and an SSE bridge. This record resolves the contradiction for the Console while leaving the public site's static deployment boundary unchanged.

## Decision

### 1. Canonical stack

`services/console` uses:

- Nuxt 4.6.2 with Vue 3 and the Nuxt 4 `app/`, `server/`, and `shared/` structure.
- Tailwind CSS v4 with CSS variables.
- shadcn-vue components, initialized with a Tailwind-v4-compatible style and the `dashboard-01` block as the initial shell.
- Geist Variable and Geist Mono, sourced from `@fontsource-variable/*`.
- Nitro as the same-origin server/BFF runtime.

The Console is not converted into a public-site route and does not share the public site's static runtime. Package name and service path remain `@ibex/console` and `services/console`.

### 2. Runtime topology

The Console is built as an SSR application with a same-origin Nitro server (`node-server` build target by default). The server owns:

- `/api/operator/*` read endpoints.
- Cookie-to-upstream forwarding.
- Upstream origin and path allowlists.
- Response validation and error normalization.
- The SSE bridge at `/api/operator/events/stream`.
- `Cache-Control: private, no-store` and `Vary: Cookie` behavior.

The browser never receives `IBEX_OPERATOR_API_ORIGIN`, bearer tokens, or organization authority. A request-supplied URL is never used as an upstream target.

This decision supersedes ADR-0078's no-BFF and Pages-only Console assumption. The public `site/` remains a static Cloudflare Pages deployment. No Console production hostname, Pages project, Kubernetes workload, or deployment promotion is claimed by this record.

### 3. Live/preview boundary

> **Amended by [ADR-0089](0089-product-shape-and-console-scope.md) §4.** The prohibition below on fixture rows is replaced by the labelled-illustrative-fixture rules in ADR-0089 §4. The live-surface prohibition stands.

Only these surfaces are live:

- D1: `/v1/operator/context`, `/overview`, `/platform/health`, `/events/stream`.
- D2: `/v1/operator/traces`, `/traces/{trace_id}`, `/traces/runs/{run_id}`.

D3+ surfaces are preview designs. They must not render fixture rows, fake metrics, fake tenants, fake credentials, or non-functional mutation flows. A preview page may describe the intended schema, show a structural blueprint, name the required owning contract, and link to an adjacent live surface.

Presentation flags are not authority. `CONSOLE_DATA_MODE=preview` no longer enables fixture data. Live reads fail closed when the operator session, upstream origin, or required contract is unavailable.

### 4. Route and status model

The Console uses clean top-level routes and 308 redirects from the legacy `/dashboard/*` tree. Every surface declares:

- Static availability: `live` or `preview`.
- Owning stage: D1, D2, D3, D4, or D6.
- Runtime state: `live`, `partial`, or `unavailable`.

A `PREVIEW` surface never becomes live merely because an upstream exists. A live route with a failed or missing contract renders an explicit unavailable state with no fallback data.

### 5. Migration method

The migration happens in place on a non-merged branch, preserving the prior implementation in git history. The legacy `services/dashboard` compatibility shell is not part of this project and is not retired by this record. Its retirement still requires the parity, rollback, and reference-removal evidence recorded in ADR-0080.

The migration removes app-imported fixtures and Next.js-only dependencies. Test fixtures remain only inside the Playwright upstream fixture and must not be importable by application code. **Amended by [ADR-0089](0089-product-shape-and-console-scope.md) §4:** preview fixture modules may remain in application code under the labelled-illustrative-fixture rules.

### 6. Authentication and mutations

This migration adds no login, signup, token issuance, step-up, or mutation flow. Live BFF endpoints require the configured operator session cookie and fail closed without it. AuthService remains the session authority. Read-only D2 requires `CONSOLE_READ_ONLY=1`.

## Consequences

- `services/console` is a Nuxt/Nitro application, not a Next.js application.
- Documentation, dependency records, CI commands, and environment names must use the Nuxt/Vue stack and the new BFF paths.
- The public site's static deployment remains unchanged.
- The Console needs a server-capable runtime; a static SPA deployment is no longer an acceptable Console topology.
- D3–D6 remain deferred and must not be promoted by the presence of designed preview pages.
- Existing Next.js-specific Console documentation becomes historical or is replaced.

## Rollback

The migration is reversible by reverting to the prior known-good Console commit. There are no data migrations, no new persistent stores, and no changes to owning API contracts. Environment variables remain compatible: `IBEX_OPERATOR_API_ORIGIN`, `IBEX_OPERATOR_SESSION_COOKIE_NAME`, and `CONSOLE_READ_ONLY` keep their meanings. The public site and `services/dashboard` are unaffected.

## References

- [ADR-0078](0078-operator-runtime-topology.md) — superseded for Console topology.
- [ADR-0080](0080-ibex-console-service-rename.md) — Console name and service boundary.
- [ADR-0087](0087-public-site-nuxt-docus-migration.md) — public-site Nuxt migration and static boundary.
- [`site/app/app.css`](../../site/app/app.css) — public-site visual tokens.
- [`site/content/docs/11.operations/08.console.md`](../../site/content/docs/11.operations/08.console.md) — Console status and data boundary.
