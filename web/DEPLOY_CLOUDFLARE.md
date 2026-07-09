# Cloudflare deployment (ibexharness.com)

The product site deploys to **Cloudflare Pages** as a pure static export (`web/out/`). Production serves **landing** at `https://ibexharness.com/` and **docs** at `https://ibexharness.com/docs/...` from one Pages project.

**Deploy pipeline:** GitHub Actions only — [`.github/workflows/web-deploy.yml`](../../.github/workflows/web-deploy.yml). Do **not** connect Cloudflare Workers Builds Git to this repo.

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

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Pages deploy (scoped token) |
| `CLOUDFLARE_ACCOUNT_ID` | Account identifier |

Never commit tokens. For local manual deploy, load both from the GitHub **production** environment secrets.

## Local development

```bash
pnpm install
pnpm web:dev   # http://localhost:3000
```

Cmd+K search in dev uses `/api/search` (live Orama). Production uses static `/search-index.json`.

### Local smoke checklist

After `pnpm web:dev`, verify:

- `/docs/getting-started/introduction`
- `/roadmap` (hub page)
- `/roadmap/current-state`
- Cmd+K search

## Local build (static export)

From repo root:

```bash
pnpm install
pnpm --filter web build:clean   # phase 1: compile + extract; phase 2: export to out/
```

On Windows, if a prior `next dev` left a lock file, stop it first:

```bash
pnpm --filter web stop:next
pnpm --filter web build:clean
```

Build phases:

1. **Phase 1** — standard Next.js build; `next start` extracts search index + OG PNGs into `public/`
2. **Phase 2** — `output: export` writes static site to `web/out/`

Preview locally with any static file server:

```bash
npx serve web/out
```

## Deploy

| Trigger | When |
| --- | --- |
| CI success on `main` | The **CI** workflow calls this reusable workflow after required jobs pass, when docs paths changed |
| `workflow_dispatch` | GitHub → Actions → **Web Deploy** → **Run workflow** (from `main` only) |

Web Deploy runs typecheck, unit tests, `build:clean`, deploys `web/out` via `wrangler pages deploy`, then smoke-tests the **Pages preview URL** (`*.pages.dev`). It does **not** HTTP-smoke the custom domain: Cloudflare WAF may return **403** to GitHub Actions datacenter IPs on `ibexharness.com` while the preview URL is healthy. Verify production manually after deploy.

**Manual (local):**

```powershell
cd ibex-harness
$env:CLOUDFLARE_API_TOKEN = "..."   # GitHub production environment secret
$env:CLOUDFLARE_ACCOUNT_ID = "..."
pnpm --filter web build:clean
pnpm --filter web deploy:pages
```

## Custom domain and DNS cutover

DNS cutover is **not** part of CI. One-time apex attach, legacy subdomain removal, and redirect rules are documented in the **private ops runbook** (outside this repository). After cutover, verify:

```bash
curl -fsSI https://ibexharness.com/
curl -fsSI https://ibexharness.com/docs/getting-started/introduction
curl -fsSI https://ibexharness.com/search-index.json
bash .github/scripts/web-smoke.sh https://ibexharness.com
```

Legacy `docs.ibexharness.com` should 301 to the same paths on apex.

### Search index URL

Cmd+K always loads **`/search-index.json`** (stable). The build also writes `search-index.<buildId>.json` for immutable CDN caching, but the client must not reference the versioned path — phase 2 static export gets a new `BUILD_ID` and the versioned file would 404.

## Redirects and cache headers

Production redirects live in [`public/_redirects`](public/_redirects) (Cloudflare Pages format). Cache headers in [`public/_headers`](public/_headers).

`next.config.mjs` redirects apply in `next dev` only.

## Remove legacy Worker (post-cutover)

After Pages is live and stable, confirm any legacy OpenNext Worker scripts are removed in the Cloudflare dashboard.
