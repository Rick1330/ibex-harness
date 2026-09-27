# Public web site (Fumadocs)

Next.js + Fumadocs application for [ibexharness.com](https://ibexharness.com). The public site and docs live under `web/`; engineering research and roadmap sources live under `web/engineering/` and `web/content/roadmap/`.

| Path | Purpose |
| --- | --- |
| `content/docs/` | Public MDX documentation (intentionally maintained in its own documentation scope) |
| `content/roadmap/` | Public roadmap and current-state source |
| `src/` | App Router, components, layout, and route behavior |
| `engineering/` | Contributor-facing architecture, contracts, operations, and research |

## Run and verify

From the repository root:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm docs:dev
```

The root route `/` renders the landing page directly; it does not redirect to an introduction page. The docs home is `/docs`, and the roadmap is `/roadmap`.

For production-like navigation and Mermaid output:

```bash
pnpm docs:build:clean
pnpm docs:start
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web test:e2e
```

Do not judge performance from `next dev`: MDX/Shiki compilation is intentionally on-demand. Never run dev, build, and start concurrently on the same port.

## Contribution boundary

Public docs content and engineering documentation are separate corpora. Do not infer current implementation status from historical milestone pages; link to the [current-state snapshot](content/roadmap/current-state.mdx) and verified source/tests. For contribution rules, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Build and deployment

```bash
pnpm docs:build
pnpm docs:build:clean
```

Deployment is performed by the tracked web workflow after required checks. The local Cloudflare/hosting runbook is intentionally external to this repository; a successful local build is not a deployment or production-origin proof.
