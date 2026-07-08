# Cloudflare deployment (ibexharness.com)

The product site deploys to **Cloudflare Pages** as a pure static export (`docs/app/out/`). Production serves **landing** at `https://ibexharness.com/` and **docs** at `https://ibexharness.com/docs/...` from one project (`ibex-harness-docs`). Legacy `docs.ibexharness.com` should 301 to the same paths on apex after cutover (see [apex-domain-cutover.mjs](scripts/apex-domain-cutover.mjs)).

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

For local manual deploy, load `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the GitHub **production** environment secrets — never commit tokens.

### API token permissions

Create at [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens):

| Permission | Access |
| --- | --- |
| Account → Cloudflare Pages | Edit |
| Account → Workers Scripts | Edit |
| Account → Workers Domains | Edit |
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
| CI success on `main` | The **CI** workflow calls this reusable workflow after required jobs pass, when docs paths changed |
| `workflow_dispatch` | GitHub → Actions → **Docs Deploy** → **Run workflow** (from `main` only) |

Docs Deploy runs typecheck, unit tests, `build:clean`, deploys `docs/app/out` via `wrangler pages deploy`, then smoke-tests the **Pages preview URL** (`*.pages.dev`). It does **not** HTTP-smoke the custom domain: Cloudflare WAF may return **403** to GitHub Actions datacenter IPs on `ibexharness.com` while the preview URL is healthy. Verify production manually after deploy (see below). DNS cutover is manual.

**Manual (local):**

```powershell
cd ibex-harness
$env:CLOUDFLARE_API_TOKEN = "..."   # GitHub production environment secret
$env:CLOUDFLARE_ACCOUNT_ID = "..."
pnpm --filter docs build:clean
pnpm --filter docs deploy:pages
```

## Custom domain

Production DNS: **`ibexharness.com`** → Cloudflare Pages project **`ibex-harness-docs`** (proxied CNAME to `ibex-harness-docs.pages.dev`).

### Apex cutover (one-time)

DNS cutover is **not** part of CI. Run [`scripts/apex-domain-cutover.mjs`](scripts/apex-domain-cutover.mjs) after merge to `main`:

1. Attach `ibexharness.com` to the Pages project
2. Ensure proxied CNAME `ibexharness.com` → `ibex-harness-docs.pages.dev`
3. Detach and delete DNS for legacy `docs.ibexharness.com`
4. Add a zone Redirect Rule: `docs.ibexharness.com/*` → `https://ibexharness.com/$1` (301) for bookmarked URLs

```bash
cd docs/app
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
node scripts/apex-domain-cutover.mjs
cd ../..
```

Verify after cutover:

```bash
curl -fsSI https://ibexharness.com/
curl -fsSI https://ibexharness.com/docs/getting-started/introduction
curl -fsSI https://ibexharness.com/search-index.json
bash .github/scripts/docs-smoke.sh https://ibexharness.com
```

### Legacy subdomain migration (historical)

The older [`scripts/pages-domain-cutover.mjs`](scripts/pages-domain-cutover.mjs) moved `docs.ibexharness.com` from OpenNext Worker to Pages. Use only when recovering that migration path — new deploys use apex cutover above.

### Search index URL

Cmd+K always loads **`/search-index.json`** (stable). The build also writes `search-index.<buildId>.json` for immutable CDN caching, but the client must not reference the versioned path — phase 2 static export gets a new `BUILD_ID` and the versioned file would 404.

## Redirects and cache headers

Production redirects live in [`public/_redirects`](public/_redirects) (Cloudflare Pages format). Cache headers in [`public/_headers`](public/_headers).

`next.config.mjs` redirects apply in `next dev` only.

## Remove legacy Worker (post-cutover)

After Pages is live and stable, confirm the OpenNext Worker script `ibex-harness-docs` is gone (the cutover script deletes it). Stray scripts to check in the dashboard: `ibex-harness`, `ibexharness`.
