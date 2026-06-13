# Phase 1.5: Docs Site

**Status:** In progress  
**Target:** [docs.ibexharness.com](https://docs.ibexharness.com)  
**Depends on:** Phase 1 complete; landing + DNS ready ([ibexdepo](https://github.com/Rick1330/marvel-scape))  
**Blocks:** [Phase 2](../phase-2-single-provider/README.md) entry (docs-first sequencing)

## Purpose

Ship a public Fumadocs documentation site at `docs.ibexharness.com` with the **Matte Graphite** design system, aligned with the marketing landing at `ibexharness.com`. Engineering docs remain in [`docs/`](../../) (ADRs, roadmap); the Fumadocs app lives in [`docs/app/`](../../app/); public MDX in [`docs/app/content/`](../../app/content/) (D.2.1+).

## Wave-based delivery

One focused PR per wave. Do not batch milestones.

| Wave | Milestones | Outcome |
| --- | --- | --- |
| 0 | (scaffold) | Roadmap, ADR-0023, governance |
| 1 | [D.1.1](milestones/d1.1-pnpm-workspace-turborepo.md), [D.1.2](milestones/d1.2-cursor-rules-editorconfig.md) | pnpm + Turborepo + Cursor rules |
| 2 | [D.2.1](milestones/d2.1-bootstrap-fumadocs.md)–[D.2.2](milestones/d2.2-matte-graphite-tokens.md), [D.2.7](milestones/d2.7-sidebar-breadcrumbs-on-this-page.md) | Design shell (design gate after D.2.2) |
| 3 | [D.2.3](milestones/d2.3-mdx-components-catalogue.md) | MDX component kit |
| 4 | [D.2.4](milestones/d2.4-dynamic-og-images.md)–[D.2.6](milestones/d2.6-enhanced-code-blocks.md) | Search, code blocks, OG |
| 5 | [D.3.1](milestones/d3.1-information-architecture-meta-json.md), [D.2.8](milestones/d2.8-not-found-home-redirect.md) | IA skeleton + 404 |
| 6–8 | [D.3.2](milestones/d3.2-seed-pages-content-stubs.md) (sections) | Content by section |
| 9 | [D.3.3](milestones/d3.3-quickstart-five-minute-path.md), [D.3.4](milestones/d3.4-api-reference-manual-phase1.md) | Quickstart + manual API |
| 10 | [D.4.1](milestones/d4.1-vercel-preview-deploys.md) | Vercel previews |
| 11 | [D.4.2](milestones/d4.2-github-actions-docs-checks.md), [D.5.2](milestones/d5.2-verify-phase15-script.md) | CI gates |
| 12 | [D.5.1](milestones/d5.1-visual-qa-sweep.md), [D.6.2](milestones/d6.2-dns-vercel-domain-attach.md)–[D.6.3](milestones/d6.3-cross-site-nav-sitemaps.md) | Production launch |

**Current wave:** 7 — [D.3.2](milestones/d3.2-seed-pages-content-stubs.md) seed content (Getting Started + Proxy + Auth done; Deployment next)

## Goals

See [goals.md](goals.md). Milestone index: [PHASE_1_5_DOCS_SITE_MILESTONES.md](PHASE_1_5_DOCS_SITE_MILESTONES.md).

## References

- [MASTER_BRIEF.md](MASTER_BRIEF.md) — design and technical spec (canonical)
- [CONTENT_SOURCES.md](CONTENT_SOURCES.md) — engineering doc → public page mapping
- [ADR-0023](../../adr/ADR-0023-docs-site-architecture.md)

## Entry criteria

- [x] Phase 1 exit complete
- [x] `ibexharness.com` live; `docs` CNAME in Cloudflare (DNS only)
- [x] Phase 1.5 roadmap scaffold merged (Wave 0)

## Exit criteria

- [ ] `https://docs.ibexharness.com` serves the Fumadocs site (200)
- [ ] Matte Graphite design passes visual QA ([D.5.1](milestones/d5.1-visual-qa-sweep.md))
- [ ] `infra/scripts/verify_phase15.sh` passes against production
- [ ] Cross-links: landing ↔ docs; both sitemaps in GSC
- [ ] `docs-checks` CI green on PRs touching `docs/app/`
