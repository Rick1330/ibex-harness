<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="public/brand/ibex-mark-dark.png">
    <img alt="IBEX Harness" src="public/brand/ibex-mark-light.png" width="96" height="96">
  </picture>
</p>

<h1 align="center">IBEX Harness Public Site</h1>

<p align="center">The static public site for IBEX Harness: landing page, documentation, blog, releases, and benchmarks.</p>

<p align="center">
  <a href="https://ibexharness.com">ibexharness.com</a> ·
  <a href="https://ibexharness.com/docs">Documentation</a> ·
  <a href="https://ibexharness.com/benchmarks">Benchmarks</a> ·
  <a href="../README.md">Repository</a>
</p>

## What this is

This directory contains the Nuxt 4 + Docus application for the public site. It is built as a
static site and deployed to Cloudflare Pages; there is no public-site server runtime.

The site is not the operator application. `services/console` is the canonical Console.

## Prerequisites

- Node.js 22 (see the repository `.nvmrc`)
- pnpm 9.15.9 (declared by the root `packageManager` field)

Run commands from the repository root unless noted otherwise.

## Local development

```bash
pnpm install
pnpm site:dev
```

`pnpm site:dev` starts Nuxt on `http://localhost:3000` by default. Use the root scripts rather
than running Nuxt directly so workspace tooling and generated release data stay consistent.

## Build and preview

```bash
pnpm site:build
pnpm site:start
```

`pnpm site:build` writes the deployable static output to `site/.output/public`. The build runs
`scripts/build-releases.mjs` first through the package `prebuild` hook.

## Verification

Run these before opening a pull request that changes the site:

```bash
pnpm site:typecheck
pnpm site:lint
pnpm site:build
pnpm site:check
pnpm --filter site exec playwright install chromium
pnpm --filter site test:e2e
```

`pnpm site:check` runs the claims, internal-link, and redirect checks. Link and redirect checks
read the built output, so run `pnpm site:build` first. Playwright starts the built server on
`127.0.0.1:3282`, so it also requires a build.

CI runs the same checks through `ci-gate-web` and `.github/workflows/site-deploy.yml`.

## Content and routing

- Reader-facing docs and blog posts live under `site/content/`.
- Pages, layouts, and interactive components live under `site/app/`.
- Pages are files under `site/app/pages/`; docs and blog routes are generated from content.
- Use absolute internal links (`/docs/...`, `/blog/...`) in content and components.
- Capability claims must carry status frontmatter (`status`, `verifiedDate`, `sourceOfTruth`) and
  stay within the evidence recorded in the status ledger.
- Architecture Decision Records are engineering records under `../engineering/adr/`. The
  `/docs/adr` route redirects to GitHub; do not add public ADR pages.
- Compatibility redirects live in `site/public/_redirects`. Every local target must resolve in
  `site/.output/public`.
- Cloudflare Pages headers and caching rules live in `site/public/_headers`.

Canonical status sources:

- `../engineering/architecture-v2/00-status-and-evidence.md`
- `site/content/docs/02.architecture/05.status-and-evidence.md`
- `site/app/data/ledger.ts`

## Deployment

`.github/workflows/site-deploy.yml` builds the site and deploys `site/.output/public` to the
Cloudflare Pages project `ibex-harness-docs`. The workflow runs after the site build and Go
quality gates on `main`, and can also be dispatched manually or called by CI.

## Layout

```text
site/
  app/                  # pages, components, layouts, styles
  content/docs/         # public documentation
  content/blog/         # published articles
  e2e/                  # Playwright browser tests
  public/               # static assets, redirects, headers, benchmark data
  scripts/              # build and validation scripts
  server/               # Nuxt/Nitro server entry for local preview and tests
```

For contributor workflow, CI gates, and commit requirements, see
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) and [`../AGENTS.md`](../AGENTS.md).
