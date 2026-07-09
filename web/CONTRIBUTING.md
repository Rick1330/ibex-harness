# Contributing to the public docs site

Fumadocs app at `docs/app/` for [docs.ibexharness.com](https://docs.ibexharness.com).

Engineering documentation (ADRs, roadmap) lives in the parent [`docs/`](../) tree — do not mix corpora.

## Dev loop

From repo root:

```bash
pnpm install
pnpm docs:dev
```

Open `http://localhost:3000` (redirects to introduction after D.2.1).

### Performance testing

`pnpm docs:dev` compiles MDX on demand — navigation will feel slow. Before reviewing nav speed or Mermaid diagrams, run:

```bash
pnpm docs:build:clean
pnpm docs:start
```

See [README.md](./README.md#performance) for details.

## Branch naming (Phase 1.5)

| Pattern | Example |
| --- | --- |
| `feat/d{N}-{slug}` | `feat/d2-2-matte-graphite` |
| `docs/phase-1-5-*` | roadmap-only PRs |

One milestone per PR. See [Phase 1.5 README](../roadmap/phase-1-5-docs-site/README.md).

## Design anti-patterns (reject in review)

- Gradients, blur, colored glow shadows
- `rounded-full` buttons, `framer-motion`, scroll reveals
- Hex colors in components (use CSS variables / Tailwind tokens)
- Default exports in components (except Next.js routes)

Full rules: [MASTER_BRIEF §0.1](../roadmap/phase-1-5-docs-site/MASTER_BRIEF.md) and `.cursor/rules/docs-site.mdc`.

## PR checklist

- [ ] Diff scoped to `docs/app/**` (or milestone docs)
- [ ] `pnpm docs:build` passes
- [ ] `pnpm --filter docs test` passes (Vitest)
- [ ] Dark + light checked on touched pages
- [ ] Navigation tested on **production server** (`build:clean` + `start`), not only `docs:dev`
- [ ] Mermaid pages visually checked after rebuild (if MDX/mermaid touched)
- [ ] PR body uses [.github/pull_request_template.md](../../.github/pull_request_template.md)

## Cloudflare deploy

See [DEPLOY_CLOUDFLARE.md](./DEPLOY_CLOUDFLARE.md) for OpenNext build, GitHub Actions deploy, and token permissions.
