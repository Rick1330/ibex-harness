# IBEX Harness — Docs Site Master Brief

> **Single source of truth** for designing, building and shipping
> `docs.ibexharness.com`. This document supersedes
> `BRAND_LANDING_DOCS_DOMAIN_SETUP.md` for everything *docs-site* related.
> The landing page is already built in a separate repository
> (this Lovable project) and is referenced here only at the boundary
> (cross-linking, shared brand, shared domain). Read this top to bottom
> **before** starting any milestone — most decisions rely on context
> defined earlier.

**Audience:** you, working in Cursor (or any LLM-pair-programming editor)
on the `ibex-harness` monorepo.
**Scope:** Phase 1.5 — Docs Site. Six goals (D.1 → D.6), 22 milestones.
**Style:** prescriptive. Where a choice is "non-negotiable" it is marked
explicitly. Where the choice is yours, alternatives are listed with the
trade-off spelled out.

---

## Table of Contents

- [0. How to drive Cursor through this document](#0-how-to-drive-cursor-through-this-document)
- [PART A — Brand System: "Matte Graphite"](#part-a--brand-system-matte-graphite)
- [PART B — Architecture & Repository Layout](#part-b--architecture--repository-layout)
- [PART C — Framework Decisions (and why)](#part-c--framework-decisions-and-why)
- [PART D — Docs Site Milestones (D.1 → D.6)](#part-d--docs-site-milestones-d1--d6)
- [PART E — Design Implementation Catalogue](#part-e--design-implementation-catalogue)
- [PART F — Information Architecture & Content Model](#part-f--information-architecture--content-model)
- [PART G — Performance, Accessibility, SEO budgets](#part-g--performance-accessibility-seo-budgets)
- [PART H — Domain, DNS & Deployment](#part-h--domain-dns--deployment)
- [PART I — Landing Page (boundary contract only)](#part-i--landing-page-boundary-contract-only)
- [PART J — Cursor Prompt Library (per milestone)](#part-j--cursor-prompt-library-per-milestone)
- [PART K — Launch Checklist](#part-k--launch-checklist)

---

## 0. How to drive Cursor through this document

Cursor's default behaviour is "implement the next thing the user asked
for." That is the wrong default for shipping a polished docs site —
without explicit constraints it will produce indigo gradients,
rounded-2xl pill buttons, `framer-motion` reveal animations, and other
hallmarks of AI-generated marketing slop. The constraints below exist to
prevent that on **every** turn.

### 0.1 The standing system prompt for Cursor

Paste the following into Cursor's **Rules → Project Rules**
(`.cursor/rules/docs-site.mdc`). It applies to every chat in this repo.

```md
---
description: IBEX Harness — Docs site build rules. Apply on every prompt.
globs: apps/docs/**/*
alwaysApply: true
---

# Operating Mindset
You are building docs.ibexharness.com — a developer-tools documentation
site that must look indistinguishable from Vercel.com, Linear.app, or
Resend.com docs. You are NOT building a marketing page. You are NOT
building a SaaS dashboard. You write deliberate, restrained code.

# Non-negotiable design rules (REJECT any code that violates these)
1. Zero gradients (no `bg-gradient-*`, no `radial-gradient()`,
   no `linear-gradient()` except a single hairline border-image if
   absolutely required).
2. Zero blur effects (`backdrop-blur-*` is banned; the only allowed
   filter is `grayscale`).
3. Zero glow (`shadow-[color]/...` colored shadows are banned;
   only neutral black/zinc shadows are allowed).
4. Sharp corners. Max `rounded-md` (6px) on panels, `rounded-sm`
   (4px) on inputs/buttons/badges, `rounded-none` on code blocks.
   NEVER `rounded-full` on a button. `rounded-full` is only valid
   on avatars, status dots, and skeleton circles.
5. Every panel/card/code-block has a visible `1px solid hsl(var(--border))`.
   Borders define structure — not shadows, not background tints.
6. Icons: `lucide-react` only, `strokeWidth={1.5}`, size 16–20px.
   No emoji in UI chrome. No filled icons.
7. Motion: 150ms ease-out on hover/focus only. No scroll-triggered
   reveals, no parallax, no `framer-motion`, no `react-spring`,
   no Lottie. The site does not animate on load.
8. Type: Geist Sans for UI, Geist Mono for code AND for any technical
   token (UUID, version, env var name, file path). Mono ligatures OFF.
9. The ONLY accent is white in dark mode / near-black in light mode.
   No brand hue. Status colors (`--success/--warning/--danger/--info`)
   exist only inside callouts/badges, never as decoration.

# Code rules
- Tailwind v3 (Fumadocs requires it). Use design tokens, never hex.
- No `style={{ ... }}` inline color/font/spacing. Use Tailwind classes
  that reference CSS variables, or `cn()` for variants.
- Server Components by default. Add `'use client'` only when a hook
  (`useState`, `useEffect`, `useTheme`) is genuinely required.
- All new components live under `apps/docs/src/components/` and are
  exported by name (no default exports except for Next.js route files).
- MDX components are registered in `apps/docs/src/mdx-components.tsx`
  and consumed everywhere via `useMDXComponents()` — never imported
  directly inside an `.mdx` file.

# When in doubt
Open the live Vercel docs (https://vercel.com/docs) and ask:
"would this exact element appear there?" If no, don't ship it.
```

### 0.2 Working loop (per milestone)

1. Open this brief and copy the relevant **PART J prompt** for the
   milestone into Cursor's chat. The prompts in Part J are tight,
   single-purpose, and pre-loaded with the Matte Graphite tokens.
2. Cursor implements. **You review the diff visually** by running
   `pnpm --filter docs dev` and clicking through the pages it touched.
3. Run the milestone's **Acceptance Criteria** checklist. Do not move
   on with any unchecked item.
4. Open a PR with the branch name from the milestone (e.g.
   `feat/d2-5-command-palette`). Squash-merge on green.

### 0.3 Anti-patterns to call out the moment you see them

If you see any of these in a Cursor diff, **stop and reject**:

- `bg-gradient-to-*`, `from-`, `via-`, `to-` color stops
- `backdrop-blur`, `bg-opacity-*` instead of `bg-[color]/[alpha]`
- `rounded-xl`, `rounded-2xl`, `rounded-full` on a non-circular element
- `text-purple-*`, `text-indigo-*`, `text-violet-*` (any of these = wrong)
- `motion.*` (framer), `whileHover`, `whileInView`, `AnimatePresence`
- `lucide-react` icons without `strokeWidth={1.5}`
- inline `style={{ background: '#...' }}`
- `<div className="bg-black">` (use `bg-canvas` or `bg-panel`)

---

## PART A — Brand System: "Matte Graphite"

The brand is intentionally severe: monochrome zinc, sharp 1px borders,
no chrome. It must be **identical** between the landing page
(`ibexharness.com`) and the docs site (`docs.ibexharness.com`) so a
visitor crossing the subdomain boundary perceives one product.

### A.1 Why this aesthetic

Three positioning targets:

1. **Vercel docs** — for the typographic restraint and code-block
   hierarchy.
2. **Linear** — for the flat panel system, 1px borders, and motion
   discipline.
3. **Resend** — for the dark-first, accent-free monochrome palette.

What this rules out (do not even prototype):

- The "AI startup" purple/indigo gradient mesh.
- Stripe-style soft-glass cards with backdrop blur.
- Notion-style emoji-led docs nav.
- Mintlify's default candy-coloured callouts (we keep callouts but
  re-skin them).

### A.2 Color tokens (canonical)

All color is defined as HSL **without** the `hsl()` wrapper, so Tailwind
v3's `hsl(var(--token) / <alpha-value>)` arithmetic works.

#### Dark mode (default)

| Token              | Value                  | Tailwind ref class      | Usage                                  |
| ------------------ | ---------------------- | ----------------------- | -------------------------------------- |
| `--canvas`         | `240 10% 4%`  (#09090b)| `bg-canvas`             | Page background                        |
| `--panel`          | `240 6% 7%`   (#121214)| `bg-panel`              | Cards, sidebars, code blocks           |
| `--panel-raised`   | `240 5% 11%`  (#18181b)| `bg-panel-raised`       | Hover, active nav item                 |
| `--border`         | `240 5% 14%`  (#222226)| `border-border`         | All borders                            |
| `--border-strong`  | `240 4% 21%`  (#33333a)| `border-border-strong`  | Focus rings                            |
| `--text-primary`   | `0 0% 98%`    (#fafafa)| `text-text-primary`     | Headings                               |
| `--text-secondary` | `240 5% 65%`  (#a1a1aa)| `text-text-secondary`   | Body                                   |
| `--text-tertiary`  | `240 4% 46%`  (#71717a)| `text-text-tertiary`    | Captions, code-block filenames         |
| `--accent`         | `0 0% 100%`   (#ffffff)| `bg-accent`             | Primary button bg, active border       |
| `--accent-fg`      | `240 10% 4%`  (#09090b)| `text-accent-fg`        | Text on `--accent`                     |

#### Light mode

| Token              | Value                   |
| ------------------ | ----------------------- |
| `--canvas`         | `0 0% 98%`    (#fafafa) |
| `--panel`          | `240 5% 96%`  (#f4f4f5) |
| `--panel-raised`   | `240 5% 90%`  (#e4e4e7) |
| `--border`         | `240 5% 90%`  (#e4e4e7) |
| `--border-strong`  | `240 5% 84%`  (#d4d4d8) |
| `--text-primary`   | `240 10% 4%`  (#09090b) |
| `--text-secondary` | `240 4% 34%`  (#52525b) |
| `--text-tertiary`  | `240 5% 65%`  (#a1a1aa) |
| `--accent`         | `240 10% 4%`  (#09090b) |
| `--accent-fg`      | `0 0% 98%`    (#fafafa) |

#### Semantic — callouts only

| Token       | Dark                | Light               |
| ----------- | ------------------- | ------------------- |
| `--success` | `142 69% 58%`       | `142 71% 35%`       |
| `--warning` | `38 92% 50%`        | `32 95% 44%`        |
| `--danger`  | `0 91% 71%`         | `0 72% 51%`         |
| `--info`    | `213 94% 68%`       | `217 91% 51%`       |

> Semantic colors **never** appear as background, accent, or
> decoration. They appear only as: 1px left border + 16px icon inside a
> `<Callout>`, or as a 1px badge ring inside a status pill.

### A.3 Typography scale

| Role             | Font            | Weight  | Size (desktop) | Tracking  | Line-height |
| ---------------- | --------------- | ------- | -------------- | --------- | ----------- |
| Display (hero)   | Geist Sans      | 700     | 56px           | `-0.02em` | 1.05        |
| H1 (page title)  | Geist Sans      | 700     | 36px           | `-0.02em` | 1.15        |
| H2               | Geist Sans      | 600     | 24px           | `-0.01em` | 1.25        |
| H3               | Geist Sans      | 600     | 18px           | `-0.005em`| 1.3         |
| Body             | Geist Sans      | 400     | 15px           | `0`       | 1.65        |
| Small / caption  | Geist Sans      | 400     | 13px           | `0`       | 1.5         |
| Label / kbd      | Geist Mono      | 500     | 11–12px        | `0.05em`  | 1           |
| Code (block+inline) | Geist Mono   | 400     | 13.5px         | `0`       | 1.65        |

**Ligatures OFF in mono.** `font-variant-ligatures: none`. In a docs
site `===`, `=>`, `!=` must remain visually unambiguous.

### A.4 Iconography

- Library: `lucide-react` (only — no `react-icons`, no `heroicons`).
- `strokeWidth={1.5}` (never default 2).
- Size: 16px in body text, 18px in buttons/nav, 20px in callout/feature
  cards, 24px in hero/empty-states.
- Color: `currentColor`. Never explicit hex.
- `aria-hidden="true"` on decorative icons; `aria-label` on icon-only
  buttons.

### A.5 Logo & wordmark

The wordmark **is** the logo. `IBEX HARNESS`, Geist Sans 700, uppercase,
`tracking-[0.05em]`, sized 13–14px in nav, 16px in footer. "IBEX" uses
`--text-primary`; "HARNESS" uses `--text-tertiary`.

Optional mark (favicon / OG corner only) — two angled strokes meeting
at a point (ibex horns / harness buckle):

```svg
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 19L11 5"  stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M19 19L13 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M11 5L13 5"  stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
</svg>
```

### A.6 Spacing & elevation

- 8px grid. Tailwind defaults are fine; never use arbitrary
  `p-[13px]`-style values.
- Section vertical rhythm: `py-16` mobile, `py-24` desktop between
  major doc sections.
- Elevation: a single, neutral shadow only — `shadow-[0_4px_12px_rgb(0_0_0_/_0.4)]`
  (dark) and `shadow-[0_4px_12px_rgb(0_0_0_/_0.08)]` (light). Reserved
  for hovered cards. Never colored.

### A.7 Motion

```css
/* The complete motion budget. Anything not on this list is banned. */
a, button, [role="button"], [data-card] {
  transition:
    background-color 150ms ease-out,
    border-color 150ms ease-out,
    color 150ms ease-out,
    opacity 150ms ease-out;
}
```

No `transform`-based animations. No `keyframes`. No scroll-triggered
reveals. The only exception is a 1.5s `pulse` on a "live" status dot
(small green circle, optional).

---

## PART B — Architecture & Repository Layout

### B.1 Repo layout (target state at end of Phase 1.5)

The IBEX Harness repository (`Rick1330/ibex-harness`) is a monorepo.
The docs site lives at `apps/docs/`. The Go proxy, auth service,
worker, and shared libraries already live where Phase 1 placed them —
this brief does not move any of them.

```
ibex-harness/
├── apps/
│   ├── proxy/                  # Phase 1 — Go LLM proxy
│   ├── auth/                   # Phase 1 — Go auth service
│   └── docs/                   # Phase 1.5 — THIS BRIEF
│       ├── content/
│       │   └── docs/
│       │       ├── getting-started/
│       │       ├── proxy/
│       │       ├── auth/
│       │       ├── deployment/
│       │       ├── api-reference/
│       │       └── changelog/
│       ├── public/
│       │   ├── favicon.ico
│       │   └── apple-touch-icon.png
│       ├── src/
│       │   ├── app/
│       │   │   ├── (home)/page.tsx        # redirect → /docs/getting-started/introduction
│       │   │   ├── docs/[[...slug]]/
│       │   │   │   ├── page.tsx
│       │   │   │   └── opengraph-image.tsx
│       │   │   ├── api/search/route.ts
│       │   │   ├── layout.tsx
│       │   │   ├── layout.config.tsx
│       │   │   ├── globals.css
│       │   │   ├── not-found.tsx
│       │   │   ├── robots.ts
│       │   │   └── sitemap.ts
│       │   ├── components/
│       │   │   ├── mdx/
│       │   │   │   ├── callout.tsx
│       │   │   │   ├── steps.tsx
│       │   │   │   ├── code-tabs.tsx
│       │   │   │   ├── endpoint.tsx
│       │   │   │   ├── badge.tsx
│       │   │   │   └── kbd.tsx
│       │   │   └── docs/
│       │   │       ├── on-this-page.tsx
│       │   │       ├── feedback.tsx
│       │   │       └── edit-on-github.tsx
│       │   ├── lib/
│       │   │   └── source.ts
│       │   └── mdx-components.tsx
│       ├── .source/                       # auto-generated by fumadocs-mdx
│       ├── source.config.ts
│       ├── tailwind.config.ts
│       ├── postcss.config.js
│       ├── next.config.mjs
│       ├── tsconfig.json
│       └── package.json
├── packages/
│   └── shared/                # cross-app utilities (logging, ids)
├── infra/
│   └── scripts/
│       └── verify_phase15.sh  # see D.5.2
├── docs/
│   └── roadmap/
│       ├── CURRENT_STATE.md
│       └── phase-1-5-docs-site/
│           └── PHASE_1_5_DOCS_SITE_MILESTONES.md
├── .github/
│   └── workflows/
│       ├── docs-deploy.yml
│       └── docs-checks.yml
├── pnpm-workspace.yaml
├── turbo.json
└── README.md
```

### B.2 Package-manager decision: **pnpm** (with Turborepo)

- pnpm — disk-efficient and strict about phantom deps; matches how
  modern Vercel/Next projects expect to be installed.
- Turborepo — caches `next build` per-app; meaningful at ~5s today,
  meaningful at ~90s by Phase 3.
- Do **not** introduce npm or yarn anywhere; lockfile conflicts will
  bite immediately.

`pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

---

## PART C — Framework Decisions (and why)

### C.1 Docs framework: **Fumadocs** (over Mintlify, Nextra, Docusaurus)

| Criterion                  | Fumadocs                    | Mintlify           | Nextra v3   | Docusaurus      |
| -------------------------- | --------------------------- | ------------------ | ----------- | --------------- |
| Self-hosted                | ✅                          | ❌ (SaaS)          | ✅          | ✅              |
| Underlying framework       | Next.js 15 App Router       | Closed             | Next.js     | React + MDX     |
| Design freedom             | Total (Tailwind tokens)     | Limited (theme)    | Good        | Hard to override|
| Cmd+K search built-in      | ✅ (Orama)                  | ✅                 | ✅          | Algolia (paid)  |
| OG image gen at edge       | ✅ (`next/og`)              | ❌                 | ✅          | Plugin          |
| MDX with custom components | ✅ first-class              | Limited            | ✅          | ✅              |
| API reference from OpenAPI | ✅ `fumadocs-openapi`       | ✅                 | Plugin      | Plugin          |
| **Verdict**                | **Pick this**               | Vendor lock        | Less polish | Heavy           |

**Decision: Fumadocs.** It gives us the Next.js App Router (which is
the same stack as the landing page → consistent mental model), zero
vendor lock-in, and a token system we can rewrite to "Matte Graphite"
without fighting the framework.

### C.2 Required dependencies (pin these versions)

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "fumadocs-ui": "^14.0.0",
    "fumadocs-core": "^14.0.0",
    "fumadocs-mdx": "^11.0.0",
    "fumadocs-openapi": "^5.0.0",
    "lucide-react": "^0.460.0",
    "next-themes": "^0.4.0",
    "geist": "^1.3.0",
    "shiki": "^1.22.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0"
  }
}
```

> **Stay on Tailwind v3.** Fumadocs UI v14's preset is built against v3.
> v4 will work eventually but introduces upgrade pain you do not need
> mid-Phase-1.5.

### C.3 Hosting: **Vercel** (no alternatives evaluated for this phase)

- Native Next 15 support.
- Edge runtime for `opengraph-image.tsx` and `/api/search`.
- Preview deploys per-PR — required for design review.
- Same vendor as v0 (used for landing page), simplifies billing.

---

## PART D — Docs Site Milestones (D.1 → D.6)

Each milestone has a **branch name**, **goal**, **deliverables**, and
**acceptance criteria**. Do not move on until every box is ticked.

### Goals overview

| Goal | Title                                       | Milestones        |
| ---- | ------------------------------------------- | ----------------- |
| D.1  | Monorepo + tooling foundation               | D.1.1, D.1.2      |
| D.2  | Fumadocs application & visual system        | D.2.1 – D.2.8     |
| D.3  | Content authoring & IA                      | D.3.1 – D.3.4     |
| D.4  | CI/CD & preview deploys                     | D.4.1, D.4.2      |
| D.5  | Verification & quality gates                | D.5.1, D.5.2      |
| D.6  | Domain, DNS & cross-site nav                | D.6.1 – D.6.3     |

---

### D.1.1 — pnpm workspace + Turborepo

**Branch:** `feat/d1-1-workspace`
**Effort:** 2 hours

**Deliverables**
- `pnpm-workspace.yaml` with `apps/*` and `packages/*`.
- `turbo.json` with a `build`, `dev`, `lint`, `typecheck` pipeline.
- Root `package.json` with workspace scripts:
  `"docs:dev": "turbo dev --filter=docs"`,
  `"docs:build": "turbo build --filter=docs"`.
- `.gitignore` updated to ignore `.source/`, `.next/`, `.turbo/`,
  `apps/*/node_modules`.

**Acceptance**
- [ ] `pnpm install` at the repo root succeeds with zero peer warnings
      blocking the install.
- [ ] `pnpm docs:dev` is a valid command (errors are OK at this stage
      because `apps/docs` doesn't exist yet — but the command must
      resolve to `turbo`).

---

### D.1.2 — Cursor project rules + EditorConfig

**Branch:** `feat/d1-2-cursor-rules`
**Effort:** 30 minutes

**Deliverables**
- `.cursor/rules/docs-site.mdc` — the contents from §0.1 of this brief.
- `.editorconfig` — 2-space indent, LF, trim trailing whitespace.
- `.nvmrc` — `20.18.0` (Vercel-compatible).
- `apps/docs/CONTRIBUTING.md` — explains the milestone branch
  naming, the "no gradients / no blurs" rule, and how to run
  `pnpm docs:dev`.

**Acceptance**
- [ ] Cursor's status bar shows "Project Rules: 1 active" when
      editing any file under `apps/docs/`.

---

### D.2.1 — Bootstrap Fumadocs application

**Branch:** `feat/d2-1-bootstrap`
**Effort:** 3 hours

**Deliverables**

`apps/docs/package.json` — dependencies pinned per §C.2.

`apps/docs/source.config.ts`:

```ts
import { defineDocs, defineConfig } from "fumadocs-mdx/config";
import { rehypeCode, remarkSteps } from "fumadocs-core/mdx-plugins";

export const docs = defineDocs({ dir: "content/docs" });

export default defineConfig({
  mdxOptions: {
    rehypePlugins: [
      [
        rehypeCode,
        {
          themes: { light: "github-light-default", dark: "github-dark-default" },
          // Keep meta strings (filename, highlight ranges) — required for D.2.6
          keepBackground: false,
        },
      ],
    ],
    remarkPlugins: [remarkSteps],
  },
});
```

`apps/docs/next.config.mjs`:

```js
import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  experimental: { typedRoutes: true },
  redirects: async () => [
    { source: "/", destination: "/docs/getting-started/introduction", permanent: false },
  ],
};

export default withMDX(config);
```

`apps/docs/src/lib/source.ts`:

```ts
import { docs } from "../../.source";
import { loader } from "fumadocs-core/source";

export const source = loader({
  baseUrl: "/docs",
  source: docs.toFumadocsSource(),
});
```

`apps/docs/src/app/docs/[[...slug]]/page.tsx` and `layout.tsx` — use
the canonical Fumadocs templates from the official starter, but **with
no inline color/style**. Every visual decision is in `globals.css` and
`tailwind.config.ts` (D.2.2/D.2.3).

Seed content: a single page at
`content/docs/getting-started/introduction.mdx` so the site renders.

**Acceptance**
- [ ] `pnpm docs:dev` boots and `http://localhost:3000` redirects
      to `/docs/getting-started/introduction`.
- [ ] The seed page renders with the default Fumadocs layout.
- [ ] No console errors, no hydration warnings.

---

### D.2.2 — Apply Matte Graphite tokens

**Branch:** `feat/d2-2-matte-graphite`
**Effort:** 4 hours
**Replaces** the indigo `--brand-h: 226` system from earlier drafts.

**Deliverables**

`apps/docs/src/app/globals.css` — the full token file. Use the
**HSL-without-wrapper** format from §A.2 so Tailwind's
`hsl(var(--token) / <alpha-value>)` works.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --canvas: 0 0% 98%;
  --panel: 240 5% 96%;
  --panel-raised: 240 5% 90%;
  --border: 240 5% 90%;
  --border-strong: 240 5% 84%;
  --text-primary: 240 10% 4%;
  --text-secondary: 240 4% 34%;
  --text-tertiary: 240 5% 65%;
  --accent: 240 10% 4%;
  --accent-fg: 0 0% 98%;

  --success: 142 71% 35%;
  --warning: 32 95% 44%;
  --danger: 0 72% 51%;
  --info: 217 91% 51%;

  /* Fumadocs UI token bridge */
  --background: var(--canvas);
  --foreground: var(--text-primary);
  --primary: var(--text-primary);
  --primary-foreground: var(--canvas);
  --muted-foreground: var(--text-secondary);
  --card: var(--panel);
  --card-foreground: var(--text-primary);
}

.dark {
  --canvas: 240 10% 4%;
  --panel: 240 6% 7%;
  --panel-raised: 240 5% 11%;
  --border: 240 5% 14%;
  --border-strong: 240 4% 21%;
  --text-primary: 0 0% 98%;
  --text-secondary: 240 5% 65%;
  --text-tertiary: 240 4% 46%;
  --accent: 0 0% 100%;
  --accent-fg: 240 10% 4%;

  --success: 142 69% 58%;
  --warning: 38 92% 50%;
  --danger: 0 91% 71%;
  --info: 213 94% 68%;
}

/* === Hard global rules — enforce the Visual Rules from §A === */

/* 1. Strip every Fumadocs gradient utility */
.fd-background-gradient,
[class*="gradient"]:not([class*="border-gradient"]) {
  background-image: none !important;
}

/* 2. Sharp corners */
.fd-card, [data-card], [data-radix-popper-content-wrapper] {
  border-radius: 6px !important;
}
button, input, textarea, select, .fd-badge, [role="button"] {
  border-radius: 4px !important;
}
pre { border-radius: 4px !important; }

/* 3. 1px borders on every panel */
pre {
  border: 1px solid hsl(var(--border)) !important;
  background-color: hsl(var(--panel)) !important;
  line-height: 1.65 !important;
}
:not(pre) > code {
  @apply rounded-[4px] px-1.5 py-0.5 text-[0.85em] font-mono;
  background-color: hsl(var(--panel-raised));
  border: 1px solid hsl(var(--border));
}

/* 4. Ligatures OFF in mono */
pre, code, kbd { font-variant-ligatures: none !important; }

/* 5. Motion budget */
a, button, [role="button"], [data-card] {
  transition:
    background-color 150ms ease-out,
    border-color 150ms ease-out,
    color 150ms ease-out,
    opacity 150ms ease-out;
}

/* 6. Elevation — neutral shadow only */
[data-card]:hover {
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.08);
}
.dark [data-card]:hover {
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.4);
}

/* 7. Scrollbar — minimal */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: hsl(var(--border-strong));
  border-radius: 4px;
}

/* 8. Focus rings */
:focus-visible {
  outline: 1px solid hsl(var(--border-strong));
  outline-offset: 2px;
  border-radius: 4px;
}

/* 9. Body baseline */
body {
  font-feature-settings: "rlig" 1, "calt" 1;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* 10. Prose width — generous for code-heavy docs */
.prose { max-width: 72ch; }
```

`apps/docs/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";
import { createPreset } from "fumadocs-ui/tailwind-plugin";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx}",
    "./content/**/*.mdx",
    "./node_modules/fumadocs-ui/dist/**/*.js",
  ],
  presets: [createPreset({ addGlobalColors: true, preset: "zinc" })],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas) / <alpha-value>)",
        panel: "hsl(var(--panel) / <alpha-value>)",
        "panel-raised": "hsl(var(--panel-raised) / <alpha-value>)",
        border: "hsl(var(--border) / <alpha-value>)",
        "border-strong": "hsl(var(--border-strong) / <alpha-value>)",
        "text-primary": "hsl(var(--text-primary) / <alpha-value>)",
        "text-secondary": "hsl(var(--text-secondary) / <alpha-value>)",
        "text-tertiary": "hsl(var(--text-tertiary) / <alpha-value>)",
        accent: "hsl(var(--accent) / <alpha-value>)",
        "accent-fg": "hsl(var(--accent-fg) / <alpha-value>)",
        success: "hsl(var(--success) / <alpha-value>)",
        warning: "hsl(var(--warning) / <alpha-value>)",
        danger: "hsl(var(--danger) / <alpha-value>)",
        info: "hsl(var(--info) / <alpha-value>)",
      },
      borderRadius: { DEFAULT: "4px", md: "6px", lg: "6px", xl: "6px" },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "Consolas", "monospace"],
      },
    },
  },
};
export default config;
```

`apps/docs/src/app/layout.tsx`:

```tsx
import { RootProvider } from "fumadocs-ui/provider";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata = {
  metadataBase: new URL("https://docs.ibexharness.com"),
  title: { default: "IBEX Harness Docs", template: "%s — IBEX Harness" },
  description: "Self-hosted LLM proxy with persistent agent memory.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="bg-canvas text-text-primary antialiased">
        <RootProvider
          search={{ options: { api: "/api/search" } }}
          theme={{ enabled: true, attribute: "class", defaultTheme: "dark" }}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
```

`apps/docs/src/app/layout.config.tsx` — wordmark nav per §A.5.

**Acceptance**
- [ ] Dark mode is the default on first visit; toggle persists across reloads.
- [ ] No element in DevTools has `border-radius` > 6px (search the
      computed styles of the rendered page).
- [ ] No element has a `background-image: linear-gradient(...)` (search
      computed styles).
- [ ] The page renders cleanly with JS disabled (verify SSR output).

---

### D.2.3 — MDX components catalogue

**Branch:** `feat/d2-3-mdx-components`
**Effort:** 1 day

**Deliverables** — every component in `apps/docs/src/components/mdx/`:

- `Callout` — variants `note | tip | warning | danger`. 1px left
  border in semantic color, 16px icon, panel background, 6px radius.
- `Steps` — vertical numbered list, square 4px-radius number badges
  (NOT circles), 1px vertical connector line.
- `CodeTabs` — Radix Tabs styled as flat top tabs with 1px bottom border
  matching the code block below; selected tab gets `bg-panel-raised`.
- `Endpoint` — used in API reference. Renders a method badge
  (`GET/POST/PUT/DELETE`) with a 1px semantic ring and the path in mono.
- `Badge` — generic small label, used for `Beta`, `New`, `Deprecated`.
- `Kbd` — `<kbd>` styled in Geist Mono with `1px solid border` and
  `bg-panel-raised`.

Registered centrally:

```tsx
// apps/docs/src/mdx-components.tsx
import defaultMdxComponents from "fumadocs-ui/mdx";
import { Callout } from "@/components/mdx/callout";
import { Steps } from "@/components/mdx/steps";
import { CodeTabs } from "@/components/mdx/code-tabs";
import { Endpoint } from "@/components/mdx/endpoint";
import { Badge } from "@/components/mdx/badge";
import { Kbd } from "@/components/mdx/kbd";
import type { MDXComponents } from "mdx/types";

export function useMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Callout, Steps, CodeTabs, Endpoint, Badge, Kbd,
    ...components,
  };
}
```

**Acceptance**
- [ ] A test MDX page using every component renders correctly in
      both themes.
- [ ] All icons inside the components use `strokeWidth={1.5}`.
- [ ] No component contains a `bg-gradient-*`, `backdrop-blur-*`, or
      `rounded-2xl` class.

---

### D.2.4 — Dynamic OG image generation

**Branch:** `feat/d2-4-og-images`
**Effort:** 1 day

Identical implementation to the previous draft (Edge route at
`apps/docs/src/app/docs/[[...slug]]/opengraph-image.tsx`), updated to
use the Matte Graphite palette: `#09090b` background, wordmark top-left,
page title bottom-left in 56px Geist Sans 700, description in 24px
`#a1a1aa`, 1px `#222226` rule between them.

**Acceptance**
- [ ] `GET /docs/getting-started/introduction/opengraph-image` returns
      a 1200×630 PNG with the wordmark and page title.
- [ ] Slack/Discord unfurl shows the card (verify by pasting into a
      private channel).
- [ ] Lighthouse SEO score on a docs page = 100.

---

### D.2.5 — Cmd+K command palette

**Branch:** `feat/d2-5-cmdk`
**Effort:** 1–2 days

- Wire `createSearchAPI("advanced", ...)` to index `structuredData`
  from each page so heading-level matches are returned.
- Re-skin the Fumadocs search dialog per §A: 1px border, 6px radius,
  `bg-panel`, no backdrop blur. Selected row uses `bg-panel-raised`.
- The default search trigger button in the nav displays a
  `<Kbd>⌘ K</Kbd>` hint on `md+` viewports.

**Acceptance**
- [ ] `Cmd+K` / `Ctrl+K` opens the dialog from any docs page.
- [ ] Querying "rate limit" returns at least one heading-level match.
- [ ] Dialog has no `backdrop-filter` (check computed style).
- [ ] Lighthouse Best Practices ≥ 95 with the dialog open.

---

### D.2.6 — Enhanced code blocks

**Branch:** `feat/d2-6-code-blocks`
**Effort:** 1 day

- Shiki themes already set in D.2.1; verify they integrate against
  `--panel` without re-injecting their own background.
- Copy button: lucide `Copy` → `Check` with a 1.5s confirm state.
  `strokeWidth={1.5}`, 14px. Position: `top-2 right-2`, opacity 0 →
  100 on `:hover` of the `pre`.
- Filename meta: ```` ```ts title="src/foo.ts" ```` renders a 28px-tall
  top bar with `bg-panel-raised`, 1px bottom border, filename in
  `text-text-tertiary text-xs font-mono`.
- Line highlight: ```` ```ts {3,7-9} ```` highlights with
  `bg-panel-raised` + 2px `border-l border-accent` on those lines.

**Acceptance**
- [ ] Filename tab renders for any block with `title="…"`.
- [ ] Copy button works (clipboard contains the unhighlighted source).
- [ ] Highlighted lines visible in both themes without any new color.

---

### D.2.7 — Sidebar, breadcrumbs, on-this-page

**Branch:** `feat/d2-7-chrome`
**Effort:** 1 day

- Sidebar: collapsible folders, active item gets `bg-panel-raised` +
  `text-text-primary`; inactive items use `text-text-secondary`.
- Breadcrumbs: above H1, mono separator `›`, max 3 levels deep.
- On-this-page (right rail, ≥`lg`): only H2 + H3, active heading uses
  `border-l border-accent` and `text-text-primary`.
- Edit-on-GitHub + Last-updated footer line on every page.

**Acceptance**
- [ ] Sidebar collapses on `<lg` and opens via a hamburger.
- [ ] Active-section scroll-spy works on a long page (test with a
      seed page that has 10+ headings).
- [ ] "Edit this page" links to the correct GitHub URL.

---

### D.2.8 — `<NotFound />` and home redirect

**Branch:** `feat/d2-8-not-found`
**Effort:** 2 hours

- `apps/docs/src/app/not-found.tsx` — centered: `404` in 72px Geist
  Mono, "Page not found" H2, two outline buttons: "Back to home"
  (`https://ibexharness.com`) and "Documentation home"
  (`/docs/getting-started/introduction`).
- Verify the `/` → `/docs/getting-started/introduction` redirect from
  D.2.1 is in effect.

**Acceptance**
- [ ] Visiting `/this-page-does-not-exist` returns the styled 404 with
      status code 404 (verify with `curl -I`).

---

### D.3.1 — Information architecture & `meta.json`

**Branch:** `feat/d3-1-ia`
**Effort:** 0.5 day

Authoritative sidebar tree (do not deviate without updating this brief):

```
Getting Started
├─ Introduction
├─ Quickstart (5 minutes)
├─ Concepts
└─ FAQ

Proxy
├─ Overview
├─ Configuration
├─ Authentication
├─ Rate Limiting
├─ Request Routing
└─ Provider Adapters

Auth
├─ Overview
├─ Issuing API Keys
├─ Org & Project Model
└─ Multi-tenant RLS

Deployment
├─ Docker Compose (dev)
├─ Kubernetes (production)
├─ Environment Variables
└─ Observability (OTel + Prometheus)

API Reference
├─ REST endpoints (generated from OpenAPI, D.3.4)
└─ Errors

Changelog
└─ (per-version pages)
```

Each folder has a `meta.json`:
```json
{ "title": "Proxy", "pages": ["overview", "configuration", "authentication", "rate-limiting", "request-routing", "provider-adapters"] }
```

**Acceptance**
- [ ] Sidebar matches the tree exactly.
- [ ] Every leaf page has frontmatter `title` and `description`.

---

### D.3.2 — Seed pages (content stubs)

**Branch:** `feat/d3-2-seed-content`
**Effort:** 1–2 days

Write a minimum viable page for **every** leaf in D.3.1. A stub is
acceptable, but every stub must contain:

- An H1 and a 1-sentence lede.
- At least one `<Callout type="note">` or `<Steps>` block.
- At least one runnable code snippet.

This forces the design system to be exercised on every page before launch.

**Acceptance**
- [ ] Every leaf renders without "page is empty" placeholder.
- [ ] `pnpm docs:build` succeeds.

---

### D.3.3 — Quickstart (5-minute path)

**Branch:** `feat/d3-3-quickstart`
**Effort:** 0.5 day

`content/docs/getting-started/quickstart.mdx` is the page most visitors
hit second. Mandatory shape:

1. **Prereqs** — bullet list (Go ≥ 1.22, Docker, an OpenAI key).
2. **Clone & boot** — single `<CodeTabs>` with `git clone … && make dev`.
3. **First request** — `<CodeTabs>` with `curl`, `node`, `python` tabs
   each making one chat completion against the proxy.
4. **What just happened** — 3-line `<Steps>` explaining auth, routing,
   memory write.
5. **Next steps** — 2 outline buttons → Concepts, Deployment.

**Acceptance**
- [ ] A new visitor can copy-paste from this page only and have a
      working response within 5 minutes.

---

### D.3.4 — API reference from OpenAPI

**Branch:** `feat/d3-4-openapi`
**Effort:** 1 day

- Add `fumadocs-openapi` dependency.
- Configure it to read `apps/proxy/openapi.yaml` (created in Phase 1).
- Generate pages under `content/docs/api-reference/`.
- Style every endpoint with `<Endpoint method="POST" path="/v1/chat/completions" />`.

**Acceptance**
- [ ] All proxy endpoints appear in the sidebar under "API Reference".
- [ ] Each endpoint page shows parameters, request body schema, and
      example responses for 200/4xx/5xx.

---

### D.4.1 — Vercel project + preview deploys

**Branch:** `feat/d4-1-vercel`
**Effort:** 1 hour (mostly UI clicks)

- Create Vercel project `ibex-harness-docs`, root directory `apps/docs`.
- Set build command `pnpm --filter docs build`, install command
  `pnpm install --frozen-lockfile`.
- Env: `NEXT_PUBLIC_SITE_URL=https://docs.ibexharness.com`.
- Confirm preview deploys appear on every PR.

**Acceptance**
- [ ] Open a throwaway PR; Vercel comment appears with preview URL;
      preview renders correctly.

---

### D.4.2 — GitHub Actions: build + link-check + lighthouse

**Branch:** `feat/d4-2-ci`
**Effort:** 0.5 day

`.github/workflows/docs-checks.yml`:

```yaml
name: docs-checks
on:
  pull_request:
    paths: ["apps/docs/**", "packages/**", "pnpm-lock.yaml"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version-file: ".nvmrc", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter docs build
      - run: pnpm --filter docs exec lychee --no-progress --exclude-mail "out/**/*.html"
  lighthouse:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: treosh/lighthouse-ci-action@v11
        with:
          urls: |
            https://ibex-harness-docs-git-${{ github.head_ref }}-rick1330.vercel.app/docs/getting-started/introduction
          configPath: ".github/lighthouse/config.json"
          uploadArtifacts: true
```

`.github/lighthouse/config.json` — assert scores: performance ≥ 90,
accessibility = 100, best-practices ≥ 95, SEO = 100.

**Acceptance**
- [ ] PR with intentionally broken link is blocked by `lychee`.
- [ ] PR with `a11y` regression is blocked by Lighthouse.

---

### D.5.1 — Visual QA sweep

**Branch:** `feat/d5-1-visual-qa`
**Effort:** 0.5 day

Open every docs page in dark + light, at 375 / 768 / 1440 widths. Check:

- No horizontal scroll.
- No element overlaps another.
- Every heading is properly anchor-linked (hover shows the `#` icon).
- Every code block has a copy button.
- Every callout uses correct semantic color.

Use Playwright for a smoke-screenshot baseline:

```ts
// apps/docs/tests/visual.spec.ts
import { test, expect } from "@playwright/test";

for (const path of [
  "/docs/getting-started/introduction",
  "/docs/proxy/overview",
  "/docs/api-reference",
]) {
  for (const theme of ["light", "dark"] as const) {
    test(`${path} (${theme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(path);
      await expect(page).toHaveScreenshot({ fullPage: true, maxDiffPixelRatio: 0.01 });
    });
  }
}
```

**Acceptance**
- [ ] Baseline screenshots committed.
- [ ] CI runs `playwright test` on PRs that touch `apps/docs/`.

---

### D.5.2 — `verify_phase15.sh`

**Branch:** `feat/d5-2-verify`
**Effort:** 2 hours

```bash
#!/usr/bin/env bash
# infra/scripts/verify_phase15.sh
set -euo pipefail

BASE="${IBEX_DOCS_URL:-http://localhost:3000}"
echo "Verifying $BASE"

# 1. Root redirects to introduction
loc=$(curl -sI "$BASE/" | awk '/^[Ll]ocation:/ {print $2}' | tr -d '\r')
[[ "$loc" == */docs/getting-started/introduction ]] || { echo "root redirect failed: $loc"; exit 1; }

# 2. Key pages return 200
for p in \
  /docs/getting-started/introduction \
  /docs/getting-started/quickstart \
  /docs/proxy/overview \
  /docs/api-reference \
  /docs/changelog \
  /robots.txt \
  /sitemap.xml ; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$p")
  [[ "$code" == "200" ]] || { echo "FAIL $p ($code)"; exit 1; }
done

# 3. 404 page returns 404
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/docs/this-does-not-exist")
[[ "$code" == "404" ]] || { echo "FAIL 404 status ($code)"; exit 1; }

# 4. OG image renders
ct=$(curl -sI "$BASE/docs/getting-started/introduction/opengraph-image" | awk '/^[Cc]ontent-[Tt]ype/ {print $2}' | tr -d '\r')
[[ "$ct" == image/png* ]] || { echo "FAIL OG content-type: $ct"; exit 1; }

# 5. Search API responds
curl -fsS "$BASE/api/search?query=auth" >/dev/null

echo "✅ Phase 1.5 verification passed"
```

**Acceptance**
- [ ] Script exits 0 against local dev.
- [ ] Script exits 0 against the Vercel preview URL.

---

### D.6.1 — Cloudflare domain purchase

**Effort:** 30 min. Buy `ibexharness.com` via Cloudflare Registrar.

### D.6.2 — DNS records & Vercel domain attach

Identical to the previous draft (apex `A 76.76.21.21`, `www CNAME
cname.vercel-dns.com`, `docs CNAME cname.vercel-dns.com`; all DNS-only
/ grey-cloud).

### D.6.3 — Cross-site nav + sitemaps

- Docs site nav contains an `ibexharness.com` external link.
- Landing site nav contains a `docs.ibexharness.com` external link.
- Both sites ship `app/robots.ts` and `app/sitemap.ts`.

---

## PART E — Design Implementation Catalogue

This part defines the **exact** visual contract of every reusable
element. When in doubt, copy these specs verbatim.

### E.1 Button system

| Variant   | BG                     | Text                | Border                       | Hover                          |
| --------- | ---------------------- | ------------------- | ---------------------------- | ------------------------------ |
| `primary` | `bg-accent`            | `text-accent-fg`    | none                         | `opacity-90`                   |
| `outline` | `bg-transparent`       | `text-text-primary` | `1px solid border`           | `bg-panel-raised`              |
| `ghost`   | `bg-transparent`       | `text-text-secondary` | none                       | `bg-panel-raised text-text-primary` |
| `danger`  | `bg-transparent`       | `text-danger`       | `1px solid danger/40`        | `bg-danger/10`                 |

Common: `h-9 px-4 text-sm font-medium rounded-[4px] inline-flex
items-center gap-2`. Icon-only: `h-9 w-9 p-0`. **No `rounded-full`.**

### E.2 Card / panel

```tsx
<div className="rounded-md border border-border bg-panel p-6">
  …
</div>
```

Hover, only if interactive:
```tsx
className="rounded-md border border-border bg-panel p-6
           transition hover:border-border-strong hover:bg-panel-raised"
```

### E.3 Callout

Visual: panel background, 1px full border, **plus** a 2px left border
in the semantic color. 16px icon at top-left, body to the right.

```tsx
<aside
  className="rounded-md border border-border bg-panel
             border-l-[2px] border-l-info
             flex gap-3 p-4 text-sm"
>
  <Info className="size-4 shrink-0 text-info" strokeWidth={1.5} />
  <div className="text-text-secondary">{children}</div>
</aside>
```

### E.4 Code block

- `<pre>`: `rounded-[4px] border border-border bg-panel text-[13.5px]
  leading-[1.65] font-mono overflow-x-auto`.
- Optional filename strip: `h-7 bg-panel-raised border-b border-border
  text-xs text-text-tertiary font-mono px-3 flex items-center`.
- Copy button: absolute `top-2 right-2 size-7 rounded-[4px] border
  border-border bg-panel-raised opacity-0 group-hover:opacity-100`.

### E.5 Sidebar item

```tsx
<a className="
  flex h-8 items-center px-3 text-sm rounded-[4px]
  text-text-secondary
  hover:bg-panel-raised hover:text-text-primary
  data-[active=true]:bg-panel-raised data-[active=true]:text-text-primary
  data-[active=true]:font-medium
">
  {title}
</a>
```

### E.6 Endpoint badge

```tsx
const tone = {
  GET:    "text-info border-info/40",
  POST:   "text-success border-success/40",
  PUT:    "text-warning border-warning/40",
  DELETE: "text-danger border-danger/40",
}[method];

<span className={cn(
  "inline-flex items-center h-6 px-2 rounded-[4px] border bg-panel",
  "text-[11px] font-mono font-medium uppercase tracking-wider",
  tone,
)}>
  {method}
</span>
```

---

## PART F — Information Architecture & Content Model

### F.1 Page frontmatter standard

```yaml
---
title: Rate Limiting
description: How IBEX enforces per-org and per-key request budgets.
---
```

Every page **must** have `title` + `description`. The description
appears in: search result subtitle, OG card subtitle, `<meta>` tag.
Limit: 160 characters.

### F.2 Content style

- Sentence-case headings ("Rate limiting", not "Rate Limiting").
- Active voice. Second person ("you configure…"), not first ("we
  configure…").
- Code examples must run as written. If they require env vars, show
  the env var being set in the same block.
- No screenshots of code (always live MDX blocks).
- Architecture diagrams: prefer flat boxes-and-arrows in JSX; if a
  raster is unavoidable, ship at 2× and use `next/image`.

### F.3 Cross-references

Use the `<Card>` and `<Cards>` MDX components from Fumadocs at the
bottom of every page to point readers to the next 2 logical pages.

---

## PART G — Performance, Accessibility, SEO budgets

### G.1 Performance budget (Lighthouse production)

| Metric                       | Target |
| ---------------------------- | ------ |
| Performance                  | ≥ 90   |
| LCP (largest contentful paint)| < 1.8s |
| TBT (total blocking time)    | < 200ms |
| CLS                          | < 0.05 |
| JS bundle (route)            | < 180 KB gzip |

Levers: server components by default, no client-side analytics SDK in
v1 (use Vercel Analytics' edge ping), no client-side framer-motion.

### G.2 Accessibility budget

- Lighthouse a11y: **100** (hard fail otherwise in CI).
- Every interactive element keyboard-reachable.
- Color contrast (axe-core): zero violations on canvas + panel
  backgrounds.
- `prefers-reduced-motion: reduce` disables the 150ms transitions
  globally.

### G.3 SEO budget

- Lighthouse SEO: **100**.
- Every page: unique `<title>`, `<meta description>`, OG tags.
- `sitemap.xml` includes every doc page.
- `robots.txt` allows everything, references the sitemap.

---

## PART H — Domain, DNS & Deployment

Identical to D.6 above. Authoritative DNS record set:

| Type    | Name   | Content                  | Proxy        | Target  |
| ------- | ------ | ------------------------ | ------------ | ------- |
| `A`     | `@`    | `76.76.21.21`            | DNS-only     | Landing |
| `CNAME` | `www`  | `cname.vercel-dns.com`   | DNS-only     | Landing (308 → apex) |
| `CNAME` | `docs` | `cname.vercel-dns.com`   | DNS-only     | Docs    |

Cloudflare proxy stays **off** for Phase 1.5. Re-evaluate after launch
if WAF/bot-protection is needed.

---

## PART I — Landing Page (boundary contract only)

The landing page is already built (this Lovable project, served from
the `ibex-harness-landing` Vercel project). Do **not** modify the
landing page from inside the docs-site work. The contracts that must
be honored on both sides:

1. **Shared brand** — the landing page and the docs page must look
   like one product. The landing page already uses the Matte Graphite
   palette (and a single ember/copper accent that does not exist on
   the docs site — that contrast is intentional: the landing page is
   marketing, the docs are reference; the docs are quieter).
2. **Cross-links** — landing nav has a "Docs" link → docs site; docs
   nav has an `ibexharness.com` link → landing.
3. **Shared domain** — see Part H.
4. **OG cards** — both sites must produce valid OG cards. Visiting
   `ibexharness.com` and `docs.ibexharness.com` in a Slack unfurl
   side-by-side should clearly show they are the same brand.

That is the entire surface. No code is shared.

---

## PART J — Cursor Prompt Library (per milestone)

Each prompt below is **self-contained**. Paste the milestone's prompt
into Cursor at the start of that branch. The Project Rules from §0.1
are already in scope and do not need to be repeated.

### J.D.2.1 — Bootstrap

> Bootstrap a Fumadocs application at `apps/docs/` per the spec in
> `DOCS_SITE_MASTER_BRIEF.md` §D.2.1. Use the exact file contents from
> the brief for `source.config.ts`, `next.config.mjs`, `src/lib/source.ts`,
> `src/app/layout.tsx`, `src/app/layout.config.tsx`. Create one seed page
> at `content/docs/getting-started/introduction.mdx` with frontmatter
> `title` + `description` and a one-paragraph body. Do not install any
> dependency not listed in §C.2. Stop after `pnpm docs:dev` boots
> cleanly and the root URL redirects to the introduction page.

### J.D.2.2 — Matte Graphite tokens

> Apply the Matte Graphite design tokens to `apps/docs/`. Copy
> `globals.css` and `tailwind.config.ts` from `DOCS_SITE_MASTER_BRIEF.md`
> §D.2.2 verbatim. Do not introduce any color outside the token set. Do
> not remove the global rules at the bottom of `globals.css` (they
> enforce sharp corners, no gradients, no blur, ligatures off). Verify
> the page renders with no element having a `border-radius` > 6px and
> no `background-image: linear-gradient`. Stop when both themes look
> correct at 1440px and 375px.

### J.D.2.3 — MDX components

> Implement every component in `DOCS_SITE_MASTER_BRIEF.md` §D.2.3 under
> `apps/docs/src/components/mdx/`. Each component is a named export.
> Use `lucide-react` icons with `strokeWidth={1.5}`. Register all of
> them in `apps/docs/src/mdx-components.tsx`. Create one demo page at
> `content/docs/_internal/component-gallery.mdx` (do not list it in any
> `meta.json`) exercising every component, and verify it renders.

### J.D.2.4 — OG images

> Implement the dynamic OG image route at
> `apps/docs/src/app/docs/[[...slug]]/opengraph-image.tsx` per
> §D.2.4. Use `next/og`'s `ImageResponse`, runtime `"edge"`. Reference
> the page metadata via `source.getPage(slug)`. Background `#09090b`,
> wordmark top-left, page title bottom-left 56px Geist Sans 700,
> description in 24px `#a1a1aa`, 1px `#222226` rule between them.
> Update `generateMetadata` in the docs page to reference the route.

### J.D.2.5 — Cmd+K

> Rewrite `apps/docs/src/app/api/search/route.ts` to pass each page's
> `structuredData` into the Orama index so heading-level matches
> appear. Re-skin the Fumadocs search dialog per §D.2.5: 1px border,
> 6px radius, `bg-panel`, no backdrop blur. Add a visible
> `<Kbd>⌘ K</Kbd>` hint to the nav search trigger on `md+` viewports.

### J.D.2.6 — Code blocks

> Style code blocks per §E.4. Implement the filename top-bar (active
> when `title="…"` meta is present), the highlight-line treatment,
> and the copy button (lucide `Copy` → `Check`, opacity 0 → 100 on
> `group-hover`, position `top-2 right-2`).

### J.D.2.7 — Site chrome

> Implement the sidebar, breadcrumbs, and on-this-page rail per
> §D.2.7 and §E.5. Sidebar is collapsible on `<lg`. The on-this-page
> rail uses scroll-spy to highlight the currently visible H2/H3 with
> a `border-l border-accent` indicator. Add an "Edit this page" link
> at the bottom of each page pointing to the GitHub source.

### J.D.2.8 — Not-found + redirect

> Create `apps/docs/src/app/not-found.tsx` matching the spec in
> §D.2.8. Verify the root redirect from `next.config.mjs` still
> resolves `/` → `/docs/getting-started/introduction`.

### J.D.3.1 — IA

> Create the folder tree and `meta.json` files under
> `apps/docs/content/docs/` exactly as listed in §D.3.1. Each leaf
> gets a stub MDX file with frontmatter only.

### J.D.3.2 — Seed content

> Fill every stub from D.3.1 with the minimum content shape in §D.3.2:
> an H1, a 1-sentence lede, one `<Callout>` or `<Steps>`, and one code
> snippet. Do not write filler prose — write the real first draft.

### J.D.3.3 — Quickstart

> Author `content/docs/getting-started/quickstart.mdx` per §D.3.3. The
> page must contain the five sections in order. Use `<CodeTabs>` for
> the "First request" section with `curl`, `node`, `python` tabs.

### J.D.3.4 — OpenAPI

> Install `fumadocs-openapi`. Configure it to read
> `apps/proxy/openapi.yaml`. Generate pages into
> `content/docs/api-reference/`. Replace the default method tag with
> the `<Endpoint>` MDX component from §E.6.

### J.D.4.1 — Vercel

> (Manual.) Create the `ibex-harness-docs` Vercel project per §D.4.1.
> No code changes here.

### J.D.4.2 — CI

> Add `.github/workflows/docs-checks.yml` and
> `.github/lighthouse/config.json` per §D.4.2. Make sure the
> Lighthouse step uses the Vercel preview URL that matches the
> current PR's branch.

### J.D.5.1 — Visual QA

> Add Playwright. Create `apps/docs/tests/visual.spec.ts` from §D.5.1.
> Generate baseline screenshots locally and commit them. Wire
> `pnpm --filter docs test:visual` into the `docs-checks.yml`
> workflow.

### J.D.5.2 — Verify script

> Add `infra/scripts/verify_phase15.sh` per §D.5.2. Mark it
> executable. Run it locally; commit only after it exits 0.

---

## PART K — Launch Checklist

Run **in order**. Do not skip ahead.

- [ ] D.1.1, D.1.2 complete.
- [ ] D.2.1 → D.2.8 complete; visual QA pass.
- [ ] D.3.1 → D.3.4 complete; every page has real (not placeholder)
      first draft.
- [ ] D.4.1 + D.4.2 green on a real PR.
- [ ] D.5.1 baseline screenshots committed.
- [ ] D.5.2 `verify_phase15.sh` exits 0 against the Vercel preview.
- [ ] D.6.1 domain purchased; nameservers active in Cloudflare.
- [ ] D.6.2 DNS records added; both Vercel projects show "Valid
      Configuration".
- [ ] D.6.3 cross-site nav + sitemaps + robots verified.
- [ ] `NEXT_PUBLIC_SITE_URL` set to `https://docs.ibexharness.com`
      on the docs Vercel project.
- [ ] Final `verify_phase15.sh` with
      `IBEX_DOCS_URL=https://docs.ibexharness.com` exits 0.
- [ ] Slack unfurl test: `docs.ibexharness.com/docs/getting-started/quickstart`
      shows the custom OG card.
- [ ] Lighthouse on production URL: Perf ≥ 90, A11y = 100,
      Best-Practices ≥ 95, SEO = 100.
- [ ] `docs/roadmap/CURRENT_STATE.md` updated:
      Phase 1.5 marked **shipped**, Phase 2 may begin.

---

### Appendix — Quick reference card (print this)

```
Background     bg-canvas        #09090b / #fafafa
Panel          bg-panel         #121214 / #f4f4f5
Hover panel    bg-panel-raised  #18181b / #e4e4e7
Border         border-border    #222226 / #e4e4e7
Strong border  border-border-strong
Heading        text-text-primary
Body           text-text-secondary
Caption        text-text-tertiary
Accent         bg-accent        white (dark) / near-black (light)

Radius         4px buttons / 6px panels / 0–4px code
Icons          lucide, strokeWidth 1.5, 16–20px
Motion         150ms ease-out, hover/focus only
Font           Geist Sans / Geist Mono (ligatures OFF)

Banned         gradients · blurs · glow · framer-motion · rounded-full ·
               rounded-2xl · purple/indigo · emoji in chrome ·
               icon-only buttons without aria-label
```
