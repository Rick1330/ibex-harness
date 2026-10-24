---
title: "ADR-0087: Public site migration to Nuxt 4 + Docus"
description: "Architecture decision record 0087: replace the Next.js/Fumadocs public site under web/ with a static Nuxt 4 + Docus site under site/, keep engineering records in engineering/, and preserve the existing Cloudflare Pages deployment boundary."
adrId: "0087"
status: "Accepted"
date: "2026-10-23"
authors: "IBEX Harness team"
---

::decision-banner{status="Accepted" date="2026-10-23" id="0087"}
::

# ADR-0087: Public site migration to Nuxt 4 + Docus

- **Status:** Accepted
- **Date:** 2026-10-23
- **Authors:** IBEX Harness team
- **Supersedes:** [ADR-0023](0023-docs-site-architecture.md) for the public site implementation and repository layout.

## Context

ADR-0023 selected a Fumadocs application on Next.js under `docs/app/`, later amended to Cloudflare Pages static export. The implementation eventually lived under `web/`, with engineering records under `web/engineering/` and public content under `web/content/`.

That layout no longer matches the repository. The public site is now a Nuxt 4 + Docus application under `site/`. The migration changes the application framework, the repository layout, the content format, and the CI job names while preserving the deployment boundary: a static Cloudflare Pages site with no public-site server runtime.

Leaving ADR-0023 as the only recorded public-site architecture would make active documentation and CI contradict the accepted decision. This record captures the replacement rather than silently rewriting ADR-0023.

## Decision

### 1. `site/` is the canonical public site

The public site lives under `site/` and uses Nuxt 4 + Docus. Its structure is:

- `site/app/` — pages, layouts, components, and styles.
- `site/content/docs/` — reader-facing documentation.
- `site/content/blog/` — published articles.
- `site/public/` — static assets, redirects, headers, and benchmark data.
- `site/scripts/` — release-data and validation scripts.
- `site/server/` — Nuxt/Nitro routes used by the static build, not a privileged public runtime.

The site remains public, static-first, and separate from the operator application. `services/console` is the canonical authenticated Console; `services/dashboard` is a temporary compatibility shell.

### 2. Engineering records move to `engineering/`

`engineering/` is the canonical contributor documentation tree. ADRs, architecture records, roadmap archives, and research provenance live there. They are not public-site routes.

The public `/docs/adr` route redirects to the GitHub ADR directory. Individual ADRs are linked by repository URL; the site does not render an ADR section.

### 3. Content uses Docus MDC

Public content is authored as Markdown with Docus MDC components. MDC component property blocks use `---` fences and indented bodies that generic Markdown linters parse as headings or code blocks. Markdownlint therefore disables `MD003` and `MD046` only for `site/content/**/*.md`; the Nuxt Content build and `pnpm site:check` remain the authoritative validation for that tree.

Internal links in content and components are absolute (`/docs/...`, `/blog/...`). Redirects remain in `site/public/_redirects`, and security/cache headers remain in `site/public/_headers`.

### 4. CI and deployment keep the public-site boundary

- The site build job is `site-build` and runs typecheck, lint, build, claims/links/redirect checks, and Playwright browser tests.
- The protected aggregate check remains `ci-gate-web`; the path-filter output remains `run_web`.
- `.github/workflows/site-deploy.yml` deploys `site/.output/public` to the existing `ibex-harness-docs` Cloudflare Pages project.
- `.github/scripts/site-smoke.sh` verifies the deployed site, including the production-claim boundary, security headers, and compatibility redirects.
- No public-site secret, privileged data access, or long-lived server runtime is introduced.

### 5. Evidence boundary is unchanged

The public site does not promote capability claims. `site/app/data/ledger.ts`, `site/content/docs/02.architecture/05.status-and-evidence.md`, and `engineering/architecture-v2/00-status-and-evidence.md` must agree. Hosted HA, measured p99 SLOs, restore drills, and end-to-end tenant-isolation acceptance remain open until the ledger records evidence.

## Consequences

- ADR-0023 is superseded for the public site; its Next.js/Fumadocs paths remain historical.
- Active documentation must use `engineering/` and `site/` paths, not `web/` paths.
- CI and local verification use root scripts: `pnpm site:typecheck`, `pnpm site:lint`, `pnpm site:build`, `pnpm site:check`, and `pnpm --filter site test:e2e`.
- Roadmap archives stay under `engineering/roadmap-archive/` and are not published as public routes.
- The site remains a static Cloudflare Pages deployment; adding a server-capable BFF would require a new decision.

## References

- [ADR-0023: Docs site architecture](0023-docs-site-architecture.md) — superseded for the public site.
- [`site/README.md`](../../site/README.md) — local development, verification, and deployment.
- [`site/nuxt.config.ts`](../../site/nuxt.config.ts) — Docus configuration, sitemap, and LLM output.
- [`.github/workflows/site-deploy.yml`](../../.github/workflows/site-deploy.yml) — Cloudflare Pages deployment.
- [`engineering/architecture-v2/00-status-and-evidence.md`](../architecture-v2/00-status-and-evidence.md) — authoritative capability status.
