# Cloudflare deployment (docs.ibexharness.com)

The docs site deploys to **Cloudflare Workers** via [@opennextjs/cloudflare](https://opennext.js.org/cloudflare) (OpenNext + static assets). GitHub Actions workflow: [`.github/workflows/docs-deploy.yml`](../../.github/workflows/docs-deploy.yml).

## API token permissions

The token in `ibexdepo/.env` used for DNS must be **upgraded** (or replaced) for deploy/cleanup. Create at [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens):

| Permission | Access |
| --- | --- |
| Account → Workers Scripts | Edit |
| Account → Workers Builds | Edit |
| Account → Account Settings | Read |
| Zone → DNS | Edit (`ibexharness.com`) |

Add the same values as GitHub repository secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

## Remove accidental Workers (one-time)

If `Workers Builds: ibex-harness` / `ibexharness` checks fail on PRs, delete the misconfigured projects:

```powershell
# From ibexdepo with a Workers-capable token in .env
.\scripts\cleanup-cloudflare-workers.ps1
```

Then in Cloudflare dashboard → **Workers & Pages** → each old project → **Settings** → **Builds** → **Disconnect** GitHub repo `Rick1330/ibex-harness`.

Production worker name: **`ibex-harness-docs`** ([`wrangler.jsonc`](wrangler.jsonc)).

## Local build

From repo root:

```bash
pnpm install
pnpm --filter docs build:clean   # Next.js SSG
pnpm --filter docs build:cf      # OpenNext bundle → docs/app/.open-next/
pnpm --filter docs preview:cf    # Local Workers runtime preview
```

OpenNext warns on native Windows; CI (Ubuntu) is the source of truth for deploy bundles.

## Deploy

**CI (main branch):** pushes touching `docs/app/**` run `docs-deploy.yml`.

**Manual:**

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
export NEXT_PUBLIC_SITE_URL=https://docs.ibexharness.com
pnpm --filter docs deploy:cf
```

## Custom domain

After the first successful deploy:

1. Workers dashboard → **ibex-harness-docs** → **Domains** → add `docs.ibexharness.com`
2. Replace the old Vercel CNAME (`docs` → `cname.vercel-dns.com`) with the record Cloudflare assigns (DNS-only / grey cloud is fine if using Worker custom domain routing)

Verify:

```bash
curl -fsS https://docs.ibexharness.com/docs/getting-started/introduction
```
