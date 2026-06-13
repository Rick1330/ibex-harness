# Phase 1.5 — Docs Site Goals

| Goal | Title | Milestones |
| --- | --- | --- |
| D.1 | Monorepo + tooling foundation | D.1.1, D.1.2 |
| D.2 | Fumadocs application and visual system | D.2.1 – D.2.8 |
| D.3 | Content authoring and IA | D.3.1 – D.3.4 |
| D.4 | CI/CD and preview deploys | D.4.1, D.4.2 |
| D.5 | Verification and quality gates | D.5.1, D.5.2 |
| D.6 | Domain, DNS, and cross-site nav | D.6.2, D.6.3 (D.6.1 domain purchase: done) |

---

## Goal D.1: Monorepo + tooling foundation

**Description:** Add pnpm workspace, Turborepo pipelines, and Cursor/editor tooling so the docs app can live in `docs/app/` alongside existing Go services without package-manager conflicts.

**Related milestones:**

- [D.1.1](milestones/d1.1-pnpm-workspace-turborepo.md)
- [D.1.2](milestones/d1.2-cursor-rules-editorconfig.md)

**Validation:** `pnpm install` at repo root succeeds; `pnpm docs:dev` resolves to Turborepo; Cursor project rules active under `docs/app/`

---

## Goal D.2: Fumadocs application and visual system

**Description:** Bootstrap a Fumadocs Next.js app and apply the Matte Graphite design system — tokens, MDX components, search, code blocks, OG images, and site chrome.

**Related milestones:**

- [D.2.1](milestones/d2.1-bootstrap-fumadocs.md) – [D.2.8](milestones/d2.8-not-found-home-redirect.md)

**Validation:** `pnpm docs:dev` renders introduction page; no gradients/blurs; Cmd+K search works; visual design matches MASTER_BRIEF Part A

---

## Goal D.3: Content authoring and IA

**Description:** Define sidebar information architecture, seed all leaf pages, author the 5-minute quickstart, and document Phase 1 proxy/auth API endpoints manually (OpenAPI generation deferred).

**Related milestones:**

- [D.3.1](milestones/d3.1-information-architecture-meta-json.md) – [D.3.4](milestones/d3.4-api-reference-manual-phase1.md)

**Validation:** Sidebar matches IA tree; every leaf renders; `pnpm docs:build` succeeds; quickstart is copy-paste runnable

---

## Goal D.4: CI/CD and preview deploys

**Description:** Wire Vercel preview deploys and GitHub Actions checks (build, link-check, Lighthouse) for every PR touching the docs app.

**Related milestones:**

- [D.4.1](milestones/d4.1-vercel-preview-deploys.md)
- [D.4.2](milestones/d4.2-github-actions-docs-checks.md)

**Validation:** Preview URL on every docs PR; broken links and a11y regressions block merge

---

## Goal D.5: Verification and quality gates

**Description:** Visual QA baselines, Playwright screenshot tests, and a production verification script that validates redirects, key pages, OG images, and search.

**Related milestones:**

- [D.5.1](milestones/d5.1-visual-qa-sweep.md)
- [D.5.2](milestones/d5.2-verify-phase15-script.md)

**Validation:** Baseline screenshots committed; `infra/scripts/verify_phase15.sh` exits 0 against preview and production

---

## Goal D.6: Domain, DNS, and cross-site nav

**Description:** Attach `docs.ibexharness.com` to Vercel, configure DNS, and wire cross-links and sitemaps between landing and docs.

**Related milestones:**

- [D.6.1](milestones/d6.1-cloudflare-domain-purchase.md) (complete — pre-work)
- [D.6.2](milestones/d6.2-dns-vercel-domain-attach.md)
- [D.6.3](milestones/d6.3-cross-site-nav-sitemaps.md)

**Validation:** Both domains show Valid Configuration in Vercel; cross-nav links work; sitemaps and robots.txt verified
