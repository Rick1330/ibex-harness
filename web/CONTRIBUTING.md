# Contributing to the public web site

The `web/` workspace is the Next.js + Fumadocs public site at [ibexharness.com](https://ibexharness.com). Engineering docs, roadmap sources, and ADR content are maintained in this repository but are distinct from the public-docs content corpus.

## Development loop

From the repository root:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm docs:dev
```

`/` renders the landing page directly, `/docs` is the docs home, and `/roadmap` is the roadmap. For production-like navigation:

```bash
pnpm docs:build:clean
pnpm docs:start
```

## Branch and tracking policy

Use the repository-wide ticket/milestone policy and conventional commit format. Keep one coherent change per PR, link the tracking issue in both directions, and use `git commit --signoff` with the contributor’s verified GitHub identity. Historical Phase 1.5 branch examples are not current naming requirements.

| Change | Primary area |
| --- | --- |
| Public docs page | `web/content/docs/` |
| Roadmap/current state | `web/content/roadmap/` |
| Engineering contract/runbook | `web/engineering/` |
| Public app route/component | `web/src/` |

Read the root [CONTRIBUTING.md](../CONTRIBUTING.md), [AGENTS.md](../AGENTS.md), [engineering index](engineering/README.md), and [current state](content/roadmap/current-state.mdx) before editing.

## Design and accessibility review

Preserve the established console/site typography, spacing, color, theme, navigation, and responsive behavior. Check keyboard navigation, focus visibility, semantic headings, reduced motion, color contrast, and WCAG 2.2 AA expectations. Do not turn fixture content or untrusted Markdown/HTML into executable UI.

## PR checks

- [ ] `pnpm --filter web typecheck`
- [ ] `pnpm --filter web test`
- [ ] `pnpm --filter web test:e2e` when routes/navigation change
- [ ] `pnpm docs:build:clean`
- [ ] Dark and light themes checked on touched pages
- [ ] Production server checked with `build:clean` + `start`
- [ ] Mermaid output checked after rebuild when MDX/diagrams change
- [ ] Repository [PR template](../.github/pull_request_template.md) completed
- [ ] No `web/content/docs/**` changes unless explicitly in scope

Cloud/host deployment runbooks may exist outside git; do not document local credentials or claim a deployment from a local build.
