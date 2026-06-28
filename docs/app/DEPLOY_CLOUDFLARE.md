# Cloudflare deployment (docs.ibexharness.com)

The docs site deploys to **Cloudflare Pages** as a pure static export (`docs/app/out/`). HTML, search index, and OG images are served from the CDN — no Worker runtime on page loads.

**Deploy pipeline:** GitHub Actions only — [`.github/workflows/docs-deploy.yml`](../../.github/workflows/docs-deploy.yml). Do **not** connect Cloudflare Workers Builds Git to this repo.

## Why Pages (not Workers + OpenNext)

Recurring **Error 1102** on the previous OpenNext Worker deployment had multiple causes:

| Symptom | Root cause | Mitigation |
| --- | --- | --- |
| Error 1102 on page views | Every HTML request routed through Worker CPU; OpenNext injected Durable Object cache handlers for ISR on a 100% SSG site | Static Pages export — CDN serves HTML directly |
| Error 1102 on `/api/search` | Per-request Orama index rebuild | Fixed: pre-built `/search-index.json` at build time |
| Slow Cmd+K search (~14 MB index) | Fumadocs `advanced` mode + full roadmap milestone indexing | Switched to `simple` mode; exclude milestone bodies (~272 KB) |
| Error 1102 on OG crawls | Runtime `/api/og/*` image generation on Worker | Pre-generated PNGs in `public/docs/*/opengraph-image.png` |

See [ADR-0023](/docs/adr/0023-docs-site-architecture) (2026-06-26 amendment) for the architecture decision.

## Secrets (GitHub Environment vault)

Deploy credentials live in GitHub → **Settings** → **Environments** → **`production`**.

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Scoped API token (see permissions below) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

For local manual deploy, use the same values from gitignored `ibexdepo/.env` — never commit tokens.

### API token permissions

Create at [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens):

| Permission | Access |
| --- | --- |
| Account → Cloudflare Pages | Edit |
| Account → Account Settings | Read |
| Zone → DNS | Edit (`ibexharness.com`) |

## Local development

```bash
pnpm install
pnpm docs:dev   # http://localhost:3000
```

Cmd+K search in dev uses `/api/search` (live Orama). Production uses static `/search-index.json`.

### Local smoke checklist

After `pnpm docs:dev`, verify:

- `/docs/getting-started/introduction`
- `/roadmap` (hub page)
- `/roadmap/current-state`
- Cmd+K search

## Local build (static export)

From repo root:

```bash
pnpm install
pnpm --filter docs build:clean   # phase 1: compile + extract; phase 2: export to out/
```

On Windows, if a prior `next dev` left a lock file, stop it first:

```bash
pnpm --filter docs stop:next
pnpm --filter docs build:clean
```

Build phases:

1. **Phase 1** — standard Next.js build; `next start` extracts search index + OG PNGs into `public/`
2. **Phase 2** — `output: export` writes static site to `docs/app/out/`

Preview locally with any static file server:

```bash
npx serve docs/app/out
```

## Deploy

| Trigger | When |
| --- | --- |
| Push to `main` | Auto when `docs/**`, root `package.json`, lockfile, turbo, or workflow changes |
| `workflow_dispatch` | GitHub → Actions → **Docs Deploy** → **Run workflow** |

CI runs typecheck, unit tests, `build:clean`, deploys `docs/app/out` via `wrangler pages deploy`, then smoke-tests the Pages preview URL and production domain.

**Manual (local):**

```powershell
cd ibex-harness
$env:CLOUDFLARE_API_TOKEN = "..."   # from ibexdepo/.env
$env:CLOUDFLARE_ACCOUNT_ID = "..."
pnpm --filter docs build:clean
pnpm --filter docs deploy:pages
```

## Custom domain

Production DNS: **`docs.ibexharness.com`** → Cloudflare Pages project **`ibex-harness-docs`**.

CI runs [`scripts/pages-domain-cutover.mjs`](scripts/pages-domain-cutover.mjs) after each deploy:

1. Remove `docs.ibexharness.com` from the legacy OpenNext Worker (if still attached)
2. Attach the custom domain to the Pages project
3. Delete Worker script `ibex-harness-docs` (OpenNext only — not the Pages project)

Manual cutover (one-time or recovery):

```bash
cd docs/app
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
node scripts/pages-domain-cutover.mjs
```

Verify:

```bash
curl -fsSI https://docs.ibexharness.com/docs/getting-started/introduction   # no x-opennext header
curl -fsSI https://docs.ibexharness.com/search-index.json
curl -fsSI https://docs.ibexharness.com/api/search   # 308 via public/_redirects → /search-index.json
bash .github/scripts/docs-smoke.sh https://docs.ibexharness.com
```

### Search index URL

Cmd+K always loads **`/search-index.json`** (stable). The build also writes `search-index.<buildId>.json` for immutable CDN caching, but the client must not reference the versioned path — phase 2 static export gets a new `BUILD_ID` and the versioned file would 404.

## Redirects and cache headers

Production redirects live in [`public/_redirects`](public/_redirects) (Cloudflare Pages format). Cache headers in [`public/_headers`](public/_headers).

`next.config.mjs` redirects apply in `next dev` only.

## Remove legacy Worker (post-cutover)

After Pages is live and stable for 24h, confirm the Worker script is gone (CI deletes it on deploy). Stray scripts to check in the dashboard: `ibex-harness`, `ibexharness`.
