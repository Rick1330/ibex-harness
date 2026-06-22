# Cloudflare deployment (docs.ibexharness.com)

The docs site deploys to **Cloudflare Workers** via [@opennextjs/cloudflare](https://opennext.js.org/cloudflare) (OpenNext + static assets).

**Deploy pipeline:** GitHub Actions only — [`.github/workflows/docs-deploy.yml`](../../.github/workflows/docs-deploy.yml). Do **not** connect Cloudflare Workers Builds Git to this repo (it misconfigures monorepo root, skips OpenNext, and duplicates failed deploys).

## Secrets (GitHub Environment vault)

Deploy credentials live in GitHub → **Settings** → **Environments** → **`production`** — not in repo-level secrets or workflow-wide `env`. GitHub encrypts environment secrets at rest and exposes an audit trail; you can add required reviewers before deploy jobs run.

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Scoped API token (Workers Scripts Edit, Account Read, Zone DNS Edit) |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

The deploy workflow passes `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` only on the deploy step (GitHub Environment `production` secrets), not to build/test steps. Cloudflare OIDC for Workers is not available yet — see [workers-sdk#11434](https://github.com/cloudflare/workers-sdk/discussions/11434). Rotate the scoped API token quarterly.

For local manual deploy, use the same values from gitignored `ibexdepo/.env` — never commit tokens.

### API token permissions

Create at [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens):

| Permission | Access |
| --- | --- |
| Account → Workers Scripts | Edit |
| Account → Account Settings | Read |
| Zone → DNS | Edit (`ibexharness.com`) |

## Remove accidental Workers (one-time)

1. **Disconnect Workers Builds Git** (if connected): Cloudflare dashboard → **Workers & Pages** → each misconfigured project → **Settings** → **Builds** → **Disconnect** `Rick1330/ibex-harness`.

2. **Delete stray worker scripts** (from `docs/app` with a Workers-capable token):

```powershell
cd docs/app
pnpm exec wrangler delete ibex-harness --force
pnpm exec wrangler delete ibexharness --force
```

Production worker name: **`ibex-harness-docs`** ([`wrangler.jsonc`](wrangler.jsonc)).

## Local development

```bash
pnpm install
pnpm docs:dev   # http://localhost:3000
```

If port 3000 is in use, stop the stale `next dev` process or use the alternate port Next.js picks.

### Local smoke checklist

After `pnpm docs:dev`, verify:

- `/docs/getting-started/introduction`
- `/roadmap` (hub page)
- `/roadmap/current-state`
- Cmd+K search (exercises `/api/search`)

## Local build (OpenNext)

From repo root:

```bash
pnpm install
pnpm --filter docs build:clean   # Next.js SSG
pnpm --filter docs build:cf      # OpenNext bundle → docs/app/.open-next/
pnpm --filter docs preview:cf    # Local Workers runtime preview
```

OpenNext warns on native Windows; CI (Ubuntu) is the source of truth for deploy bundles.

Root [`.npmrc`](../../.npmrc) uses `node-linker=hoisted` so OpenNext can bundle the pnpm monorepo on Workers ([opennextjs-cloudflare#719](https://github.com/opennextjs/opennextjs-cloudflare/issues/719)).

## Deploy

| Trigger | When |
| --- | --- |
| Push to `main` | Auto when `docs/**`, root `package.json`, lockfile, turbo, or workflow changes |
| `workflow_dispatch` | GitHub → Actions → **Docs Deploy** → **Run workflow** (test before DNS) |

CI skips `docs-build` on pull requests that do not touch docs paths (`detect-changes` job). Deploy uses pnpm + Next.js caches and runs a post-deploy smoke test on `*.workers.dev`.

**Manual (local):**

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
export NEXT_PUBLIC_SITE_URL=https://docs.ibexharness.com
pnpm --filter docs deploy:cf
```

**Correct build chain** (CI runs this from repo root):

```bash
pnpm install --frozen-lockfile
pnpm --filter docs build:clean
pnpm --filter docs build:cf
pnpm --filter docs deploy:cf
```

Do **not** use `pnpm --filter docs build` alone for Cloudflare (missing OpenNext). Do **not** run `npx wrangler deploy` from the repo root.

## Custom domain

Production DNS is **live** at `https://docs.ibexharness.com` (Cloudflare Worker `ibex-harness-docs`).

For a new environment or disaster recovery:

1. Workers dashboard → **ibex-harness-docs** → **Domains** → add `docs.ibexharness.com`
2. Point the `docs` CNAME to the record Cloudflare assigns (DNS-only / grey cloud)

Verify:

```bash
curl -fsS https://docs.ibexharness.com/docs/getting-started/introduction
curl -fsS https://docs.ibexharness.com/roadmap
```
