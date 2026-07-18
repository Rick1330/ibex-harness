# Ibex Harness — Design System & Landing Page Specification

> A complete, implementation-ready design spec for `ibexharness.com`.
> Target stack: **Next.js 15 (App Router) + React 19 + Tailwind CSS v4 + shadcn/ui + Framer Motion**.
> Aesthetic bar: **Stripe · Anthropic · Vercel · Linear · Resend**. Editorial, technical, quiet, expensive.
> Deliverable: a single source of truth for the landing page, the docs site, the blog, benchmarks, and changelog — light + dark, fully themed, fully animated.

---

## 0. Design Principles

1. **Editorial before decorative.** Type does the heavy lifting. Color is used sparingly.
2. **Documentation-first density.** Marginal § numerals, hairline rules, mono captions. The site should look like it was written, not designed.
3. **One accent, used with restraint.** No purple gradients. No glass. No neon. No "AI slop".
4. **Motion serves reading, not itself.** Entries fade + rise 8–12px. No parallax. No confetti. No scroll-jacking.
5. **Perfect parity in dark mode.** Dark is not "light with inverted colors" — it is separately tuned (warmer paper → cooler ink).
6. **Everything is a token.** Zero hardcoded hex in components. Ever.

---

## 1. Color System

Two palettes, hand-tuned in **OKLCH** for perceptual uniformity. The accent is **Ember** — a single warm signal color that reads as ink on paper and glows in the dark. It's distinctive (not blue, not purple, not green) and works across docs, code, benchmarks, and marketing.

### 1.1 Light — "Paper"

| Token | OKLCH | Hex (approx) | Purpose |
|---|---|---|---|
| `--background` | `oklch(0.980 0.004 90)` | `#faf9f6` | Page paper |
| `--surface-1` | `oklch(0.955 0.006 88)` | `#f2efe8` | Cards, code blocks |
| `--surface-2` | `oklch(0.925 0.008 85)` | `#e6e2d8` | Sunken wells |
| `--border` | `oklch(0.28 0 0 / 0.10)` | — | Hairlines |
| `--border-strong` | `oklch(0.28 0 0 / 0.22)` | — | Emphasized rules |
| `--foreground` | `oklch(0.185 0 0)` | `#141414` | Body ink |
| `--foreground-muted` | `oklch(0.48 0 0)` | `#6b6b6b` | Captions, mono eyebrows |
| `--foreground-subtle` | `oklch(0.62 0 0)` | `#9a9a9a` | Placeholders |
| `--accent` | `oklch(0.62 0.17 45)` | `#d0562a` | Ember — links, focus, key numbers |
| `--accent-hover` | `oklch(0.56 0.18 42)` | `#b8451f` | |
| `--accent-soft` | `oklch(0.62 0.17 45 / 0.10)` | — | Tag chips, selection halo |
| `--success` | `oklch(0.58 0.12 155)` | `#3f8a5e` | Status dots, +diff |
| `--warning` | `oklch(0.72 0.14 75)` | `#c89a3a` | Deprecations |
| `--danger` | `oklch(0.55 0.20 25)` | `#c0392b` | -diff, errors |
| `--info` | `oklch(0.55 0.11 235)` | `#3d6b9a` | Info callouts |

### 1.2 Dark — "Ink"

Warm-black background (not pure `#000`), cool bone foreground — the reverse temperature of light mode. This is the trick that makes dark mode feel *designed*, not inverted.

| Token | OKLCH | Hex (approx) | Purpose |
|---|---|---|---|
| `--background` | `oklch(0.145 0.004 60)` | `#131210` | Page ink |
| `--surface-1` | `oklch(0.185 0.005 60)` | `#1b1a17` | Cards, code blocks |
| `--surface-2` | `oklch(0.22 0.005 60)` | `#22201d` | Sunken wells, terminal |
| `--border` | `oklch(1 0 0 / 0.08)` | — | Hairlines |
| `--border-strong` | `oklch(1 0 0 / 0.18)` | — | Emphasized rules |
| `--foreground` | `oklch(0.955 0.006 88)` | `#f2efe8` | Body bone |
| `--foreground-muted` | `oklch(0.68 0.005 80)` | `#a6a29a` | Captions |
| `--foreground-subtle` | `oklch(0.52 0.005 80)` | `#7a7770` | Placeholders |
| `--accent` | `oklch(0.72 0.16 48)` | `#e87a44` | Ember — lifted for dark |
| `--accent-hover` | `oklch(0.78 0.15 50)` | `#f39560` | |
| `--accent-soft` | `oklch(0.72 0.16 48 / 0.14)` | — | |
| `--success` | `oklch(0.72 0.14 155)` | `#5db084` | |
| `--warning` | `oklch(0.80 0.14 80)` | `#e0b558` | |
| `--danger` | `oklch(0.68 0.18 25)` | `#e07158` | |
| `--info` | `oklch(0.72 0.11 235)` | `#7ba8d4` | |

### 1.3 Rules
- **Never** use `text-white`, `bg-black`, `text-gray-500`, or hex literals in components. Only semantic tokens.
- Accent (Ember) appears at most **once per fold** — a link, a number, or a status dot. Not all three.
- Selection uses `--foreground` on `--background` swap (inverted), not accent-tinted.
- Focus ring: `2px solid var(--accent)` with `2px` offset — always visible, never suppressed.

---

## 2. Typography

Three families, one voice.

| Role | Family | Weights | Notes |
|---|---|---|---|
| Display | **Instrument Serif** | 400, 400 italic | Headlines only. `letter-spacing: -0.02em`. Italics for emphasis words. |
| Body / UI | **Inter** (or Inter Variable) | 400, 500, 600 | Feature flags: `"cv11","ss01","ss03"`. `letter-spacing: -0.01em` on ≥18px. |
| Mono | **JetBrains Mono** | 400, 500 | Code, eyebrows (§01), terminal, tabular numerals, keyboard shortcuts. |

**Type scale** (fluid, using `clamp`):

```css
--text-xs:    0.75rem;                                    /* 12 */
--text-sm:    0.875rem;                                   /* 14 */
--text-base:  1rem;                                       /* 16 */
--text-lg:    1.125rem;                                   /* 18 */
--text-xl:    1.375rem;                                   /* 22 */
--text-2xl:   1.75rem;                                    /* 28 */
--text-3xl:   clamp(2rem, 1.6rem + 1.4vw, 2.75rem);       /* 32→44 */
--text-4xl:   clamp(2.75rem, 2rem + 3vw, 4.25rem);        /* 44→68 */
--text-hero:  clamp(3.5rem, 2rem + 6vw, 6.5rem);          /* 56→104 */
```

**Rules**
- H1 is Instrument Serif at `--text-hero`, leading `0.95`, tracking `-0.03em`.
- Body copy caps at `62ch` — reading measure. Never full-bleed prose.
- Mono eyebrows: uppercase, `letter-spacing: 0.14em`, `--text-xs`, `--foreground-muted`.
- Numbers in benchmarks/stats: JetBrains Mono, `font-variant-numeric: tabular-nums`, weight 500.

---

## 3. Layout & Grid

- **Max content width**: `1200px` (`--container`).
- **Grid**: 12 columns, `24px` gutter desktop / `16px` mobile.
- **Vertical rhythm**: section padding `clamp(6rem, 4rem + 5vw, 10rem)` top & bottom.
- **Rail**: left margin holds `§01`, `§02` mono numerals at `-64px` from content on ≥lg, inline above title on <lg.
- **Hairlines only**: `1px solid var(--border)`. No shadows on layout. No rounded corners > `6px`.

---

## 4. Motion

Library: **Framer Motion**. Timing: `ease-out-expo` = `cubic-bezier(0.19, 1, 0.22, 1)`.

| Pattern | Spec |
|---|---|
| Section entry | `opacity 0→1`, `y 12→0`, `duration 700ms`, `stagger 60ms` for children |
| Link hover | Underline draws L→R, `duration 240ms`, `ease-out` |
| Button hover | `background` shift only, `duration 160ms`. No lift, no shadow. |
| Terminal caret | 1.1s step-blink, infinite |
| Marquee tags | 40s linear infinite, paused on hover |
| Theme toggle | Crossfade `background`/`color` at `duration 300ms` — no whole-page flash |
| Number counters (benchmarks) | Count-up on in-view, `duration 1200ms`, tabular-nums |
| Route change (docs) | 120ms fade only. No slide. |

**Reduced motion**: honor `prefers-reduced-motion: reduce` — disable marquee, counters, entry translate. Keep opacity fades ≤ 200ms.

---

## 5. Theme Switcher

Three-state: **System · Light · Dark**. Implementation: `next-themes` with `attribute="class"` and `disableTransitionOnChange={false}` — we *want* a 300ms crossfade.

**Placement**: top-right of the header, next to GitHub link. Icon-only, `28×28`, keyboard accessible, `aria-label="Toggle theme"`. Cycles System → Light → Dark → System. Icon reflects current resolved theme (sun/moon/monitor).

```tsx
// components/theme-toggle.tsx — sketch
"use client";
import { useTheme } from "next-themes";
import { Sun, Moon, Monitor } from "lucide-react";

const order = ["system", "light", "dark"] as const;
export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const Icon = theme === "system" ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  const next = () => setTheme(order[(order.indexOf((theme as any) ?? "system") + 1) % 3]);
  return (
    <button onClick={next} aria-label="Toggle theme"
      className="grid place-items-center h-8 w-8 rounded-sm text-foreground-muted hover:text-foreground hover:bg-surface-1 transition-colors">
      <Icon className="h-4 w-4" />
    </button>
  );
}
```

Root layout must render `<html suppressHydrationWarning>` and wrap children in `<ThemeProvider attribute="class" defaultTheme="system" enableSystem>`.

Add a `no-flash` inline script in `<head>` that reads `localStorage.theme` and sets `document.documentElement.classList` before hydration — prevents the white flash on dark-mode reload.

---

## 6. Landing Page — Section-by-Section

The register is **documentation-first**: mono §-numerals live in the left rail; each section reads like a spec.

### §00 · Header (sticky, translucent, bottom-hairline)
- Left: wordmark `ibex` in Instrument Serif italic + `harness` in Inter 500, `20px`. Small ember dot between.
- Center (desktop only): nav — `Docs · Benchmarks · Changelog · Blog · GitHub`. Inter 500, 14px, `--foreground-muted` → `--foreground` on hover with L→R underline.
- Right: **`v0.4.2`** mono badge · Theme toggle · `★ 2.3k` GitHub star count (live via GitHub API, ISR cached 1h) · Primary CTA `Get started →`.
- Backdrop: `background/70` + `backdrop-blur-md` + `border-b border-border`.
- Shrinks by 8px on scroll (subtle).

### §01 · Hero
Two-column, 7/5 split on desktop, stacked on mobile.

**Left (7 cols):**
- Mono eyebrow: `§01 · CONTROL PLANE`
- H1 (Instrument Serif, hero size):
  > The control plane for agents that call LLMs *in production.*
  (Italic on "in production". Ember-underlined on hover of the whole H1 is **forbidden** — no gimmicks.)
- Deck (`--text-lg`, `--foreground-muted`, max `52ch`):
  > Open-source OpenAI-compatible proxy. Intercept every model request, validate tenant identity, enforce policy, and prepare memory context — at the proxy, not in glue code.
- CTAs (row, `gap-3`):
  - Primary: `Get started` — solid `--foreground` bg, `--background` text, 40px tall, 20px x-padding, `radius-sm`.
  - Secondary: `Read the spec →` — ghost, `--border` outline.
  - Tertiary (mono, muted): `curl -fsSL ibex.sh | sh` with copy icon.
- Trust row (mono, `--text-xs`, `--foreground-muted`, no logos): `MIT · Self-hostable · SOC 2 aligned · No vendor lock-in`.

**Right (5 cols) — the "something on the right" the user asked for:**
A **live-looking terminal card** with tabs `request.http` / `response.json` / `trace.log`. Content cycles every 6s with a subtle crossfade. Card: `--surface-1` bg, `1px --border`, `radius-md`, mono `13px`, tabular nums, syntax-highlighted with token colors from the palette (accent = strings/keys of interest, muted = punctuation, foreground = identifiers). Above the tabs: three window dots in `--foreground-subtle` and a filename `~/ibex/trace-7f3a…c21`. Below: a footer strip showing `P99  17ms` · `tenant  acme-prod` · `model  gpt-4o` in mono.

Alternate right-side content option: a **request-path SVG diagram** (Client → Ibex → Provider) with an animated dashed line traversing on scroll. Pick terminal for launch; diagram appears again in §03.

### §02 · Capabilities (2×2 bento, hairlines, no shadows)
Eyebrow `§02 · CAPABILITIES`. Grid of four cards, each: mono index `01–04`, Instrument Serif 28px title, Inter body (`52ch`), one mono code fragment at the bottom (`bg-surface-2`, `--text-xs`).

1. **Ingress Proxy** — OpenAI-compatible endpoints on your domain. Drop-in swap.
2. **Tenant Auth** — Per-org keys, JWT claims, RLS-safe request context.
3. **Memory Path** — Attach retrieved context at the proxy. Redis + pgvector adapters.
4. **Telemetry** — OTLP traces, per-tenant cost & latency, error taxonomy.

Cards animate in on scroll with 60ms stagger. Hover: `--border` → `--border-strong`, 160ms.

### §03 · Request Path (horizontal trace)
Eyebrow `§03 · REQUEST PATH`. Full-bleed card, `--surface-1`. Top strip: `trace_id  7f3a…c21   ·   duration  17.4ms   ·   status  200`. Below: 4 numbered pill-nodes connected by a hairline with a moving ember dot cycling L→R every 3s:

`01 authenticate → 02 rate-limit → 03 retrieve memory → 04 forward upstream`

Under each node, a 3-line mono snippet (JWT claims, quota, vector top-k, upstream host). This is the page's showpiece — spend polish here.

### §04 · Benchmarks (numbers-forward)
Eyebrow `§04 · BENCHMARKS`. Four stat cells across, hairline-divided:

| P99 overhead | Throughput | Memory | Cold start |
|---|---|---|---|
| `17ms` | `12.4k rps` | `48 MiB` | `120ms` |

Numbers in mono, tabular, Instrument Serif not used here (we want machine-precise). Below the row, a compact bar chart (SVG, tokens-only colors) comparing Ibex vs "app-code integration" across latency, complexity, and observability. Chart animates from 0 on in-view.

Small link: `See full methodology → /benchmarks`.

### §05 · Local Stack
Two columns. Left: prose list of services (Postgres, Redis, OTLP collector, Ibex core, Ibex admin UI). Right: `docker-compose up` terminal output with typed-in feel (characters reveal at 12ms/char, one-shot on in-view, respect reduced-motion).

### §06 · From the Spec (excerpts)
Editorial section: three pull-quotes from the docs in Instrument Serif italic, `--text-2xl`, each with a `→ Read section` link. This positions Ibex as documented, serious infrastructure.

### §07 · Changelog Peek
Latest 3 changelog entries, pulled from `/changelog` MDX at build time. Format: mono date (`2026.07.14`), Instrument Serif title, one-line summary, `+N/-N` diff pill. Link: `Full changelog →`.

### §08 · Closing CTA
Full-bleed dark band (uses `--foreground` bg, `--background` text — inverted, both themes). Instrument Serif headline: *"Put agent memory at the proxy."* Two CTAs. Mono footnote: `MIT · v0.4.2 · Built for teams shipping agents.`

### §09 · Footer
Four columns: **Product** (Docs, Benchmarks, Changelog, Roadmap) · **Community** (GitHub, Discord, X) · **Company** (Blog, About, Contact) · **Legal** (License, Security, Privacy). Bottom strip: mono copyright · commit SHA · `● All systems operational` (live status dot from `/api/status`).

---

## 7. Section Chrome (the "shell sections" upgrade)

Every section shares this chrome — this is what the user asked to upgrade:

```text
┌── §0X · SECTION LABEL ────────────────────────────────────  hh:mm UTC ──┐
│                                                                          │
│   [content]                                                              │
│                                                                          │
└──────────────────────────────────────────────────────────  ref /docs/§ ──┘
```

- Top-left: `§0X · LABEL` in mono uppercase, `--foreground-muted`.
- Top-right: a mono meta slot (build time, doc ref, or trace id — section-appropriate).
- Corners: **not** literal box drawing — use `1px --border` top + bottom hairlines that extend to container edges, with `4px` tick marks at the corners.
- Left rail (≥lg): the section number sticks (`position: sticky; top: 96px`) as you scroll through the section, then releases.
- Bottom-right: a small `↗` link back to the relevant doc/reference.

This gives every section a "spec sheet" chrome without a single shadow or gradient.

---

## 8. Component Library (shadcn/ui — themed)

Install via shadcn CLI, then override tokens. Keep the primitive set minimal:

- `Button` — variants: `solid` (fg bg), `outline` (border), `ghost`, `link`. Sizes: `sm 32`, `md 40`, `lg 48`. No `default` gradient.
- `Badge` — mono, uppercase, tracking `0.12em`, `--text-xs`, `--surface-1` bg.
- `Tabs` — underline variant only. Active: `--foreground` + `2px --accent` underline.
- `Card` — hairline border, no shadow, `radius-sm`.
- `Input` / `Textarea` — hairline, focus ring `--accent`.
- `Dialog` — backdrop `--background/70` + blur, `--surface-1` panel.
- `DropdownMenu` — `--surface-1`, hairline, no shadow.
- `Toast` — `--surface-1`, hairline, mono meta line.
- `Tooltip` — `--foreground` bg, `--background` text, mono `12px` — inverted, distinct.
- `Kbd` — mono, `--surface-2`, `1px --border-strong`, `radius-xs`.
- `CodeBlock` — custom. Shiki with two themes (`github-light`, `github-dark`) but override background to `--surface-1` and comment color to `--foreground-subtle`.

---

## 9. Docs Site

Framework: **Fumadocs** (Next.js-native, MDX, App Router). Layout:

- Left sidebar (`260px`): section tree, mono section numbers, current section indicator = 2px ember bar on the left edge.
- Center (`720px` max): MDX prose. Instrument Serif h1/h2, Inter body, JetBrains Mono inline code with `--surface-1` bg + `0.15em` padding.
- Right sidebar (`220px`): table of contents, scrollspy-highlighted with `--accent`.
- Callouts: `Note` (info), `Warn` (warning), `Danger` — hairline left border in accent color, no filled background.
- Code blocks: Shiki, filename tab, copy button, line numbers optional, diff highlighting for `+/-` lines.
- Search: `Cmd+K` palette (cmdk), `--surface-1`, mono results with breadcrumbs.
- API reference pages: 2-col — prose left, request/response tabs right (sticky).

---

## 10. Blog

- Index: single column, `680px`. Each entry: mono date, Instrument Serif italic title (`--text-2xl`), 2-line dek, author + read time in mono. Hairline between entries.
- Post: hero title `--text-4xl`, cover image optional (16:9, `radius-md`, `1px --border`), body prose 62ch. Footnotes and marginalia use mono in the left rail on desktop.

---

## 11. Benchmarks

Dedicated `/benchmarks` route:
- Hero table with sortable columns (workload, P50, P95, P99, throughput, cost).
- Small-multiples chart grid (recharts, tokens-only).
- Methodology accordion.
- "Run it yourself" section with a copy-pasteable script.
- Numbers everywhere are mono, tabular, and animate count-up on scroll.

---

## 12. Changelog

`/changelog` — reverse-chronological. Each release:
- Mono version + ISO date pinned to a sticky left rail.
- Instrument Serif title.
- Grouped sections: `Added` / `Changed` / `Fixed` / `Deprecated` — each with a colored dot (success/info/warning/danger) and hairline underline.
- Individual bullets in Inter, code references in mono with links to the commit.
- RSS + Atom feeds. `og:image` per release generated from the title.

---

## 13. Accessibility

- All interactive elements ≥ 44×44 touch target.
- Focus ring always visible (`outline: 2px solid var(--accent); outline-offset: 2px`). Never `outline: none` without a replacement.
- Color contrast: body text ≥ 7:1, UI ≥ 4.5:1 — the palette above hits this in both modes.
- `prefers-reduced-motion` honored globally.
- All icons have `aria-label` or are `aria-hidden` when decorative.
- Skip link at top of every page.

---

## 14. Performance

- **CLS < 0.02** — reserve space for the terminal card and stat numbers.
- **LCP < 1.5s** — hero H1 is text, not image. Fonts preloaded with `font-display: swap`.
- Self-host fonts via `@fontsource-variable/*` — no runtime Google Fonts fetch.
- Ship Framer Motion features via `LazyMotion` + `domAnimation`.
- Images: `next/image`, AVIF+WebP, `sizes` set per breakpoint.
- Route-level MDX bundling for blog/changelog. ISR for GitHub star count and status dot.

---

## 15. SEO & Metadata

- Per-route `metadata` export in Next.js App Router.
- Titles: `<page> — Ibex Harness` (< 60 chars).
- Descriptions: hand-written, < 160 chars.
- `og:image`: generated with `next/og` per route. Template: paper background, section §-numeral, Instrument Serif title, mono url footer. Dark variant for `?theme=dark`.
- JSON-LD: `SoftwareApplication` on home, `TechArticle` on docs, `BlogPosting` on blog, `Release` on changelog entries.
- Sitemap + robots via `app/sitemap.ts` / `app/robots.ts`.
- Canonical tags on every page.

---

## 16. File Structure (Next.js 15 App Router)

```text
app/
  (marketing)/
    page.tsx                 # landing
    benchmarks/page.tsx
    changelog/page.tsx
    blog/[slug]/page.tsx
    layout.tsx               # header + footer
  docs/
    [[...slug]]/page.tsx     # fumadocs
    layout.tsx
  api/
    stars/route.ts           # GitHub stars, revalidate 3600
    status/route.ts          # systems status dot
  layout.tsx                 # <html>, ThemeProvider, no-flash script
  globals.css                # @import "tailwindcss"; tokens; base
  opengraph-image.tsx        # og:image template
components/
  chrome/
    section-shell.tsx        # §-numbered section wrapper
    marquee.tsx
    terminal-card.tsx
    request-path.tsx
    counter.tsx
  ui/                        # shadcn primitives, retokenized
  theme-toggle.tsx
  header.tsx
  footer.tsx
content/
  blog/*.mdx
  changelog/*.mdx
  docs/**/*.mdx
lib/
  fonts.ts                   # @fontsource-variable imports
  mdx.ts
  github.ts
styles/
  tokens.css                 # :root and .dark token blocks
```

---

## 17. `globals.css` — Complete Token File

```css
@import "tailwindcss";
@import "@fontsource/instrument-serif/400.css";
@import "@fontsource/instrument-serif/400-italic.css";
@import "@fontsource-variable/inter";
@import "@fontsource-variable/jetbrains-mono";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-foreground-muted: var(--foreground-muted);
  --color-foreground-subtle: var(--foreground-subtle);
  --color-surface-1: var(--surface-1);
  --color-surface-2: var(--surface-2);
  --color-border: var(--border);
  --color-border-strong: var(--border-strong);
  --color-accent: var(--accent);
  --color-accent-hover: var(--accent-hover);
  --color-accent-soft: var(--accent-soft);
  --color-success: var(--success);
  --color-warning: var(--warning);
  --color-danger: var(--danger);
  --color-info: var(--info);

  --font-display: "Instrument Serif", ui-serif, Georgia, serif;
  --font-sans: "Inter Variable", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono Variable", ui-monospace, SFMono-Regular, monospace;

  --radius-xs: 2px;
  --radius-sm: 4px;
  --radius-md: 6px;

  --ease-out-expo: cubic-bezier(0.19, 1, 0.22, 1);
  --container: 1200px;
}

:root {
  --background:         oklch(0.980 0.004 90);
  --surface-1:          oklch(0.955 0.006 88);
  --surface-2:          oklch(0.925 0.008 85);
  --border:             oklch(0.28 0 0 / 0.10);
  --border-strong:      oklch(0.28 0 0 / 0.22);
  --foreground:         oklch(0.185 0 0);
  --foreground-muted:   oklch(0.48 0 0);
  --foreground-subtle:  oklch(0.62 0 0);
  --accent:             oklch(0.62 0.17 45);
  --accent-hover:       oklch(0.56 0.18 42);
  --accent-soft:        oklch(0.62 0.17 45 / 0.10);
  --success:            oklch(0.58 0.12 155);
  --warning:            oklch(0.72 0.14 75);
  --danger:             oklch(0.55 0.20 25);
  --info:               oklch(0.55 0.11 235);
}

.dark {
  --background:         oklch(0.145 0.004 60);
  --surface-1:          oklch(0.185 0.005 60);
  --surface-2:          oklch(0.22 0.005 60);
  --border:             oklch(1 0 0 / 0.08);
  --border-strong:      oklch(1 0 0 / 0.18);
  --foreground:         oklch(0.955 0.006 88);
  --foreground-muted:   oklch(0.68 0.005 80);
  --foreground-subtle:  oklch(0.52 0.005 80);
  --accent:             oklch(0.72 0.16 48);
  --accent-hover:       oklch(0.78 0.15 50);
  --accent-soft:        oklch(0.72 0.16 48 / 0.14);
  --success:            oklch(0.72 0.14 155);
  --warning:            oklch(0.80 0.14 80);
  --danger:             oklch(0.68 0.18 25);
  --info:               oklch(0.72 0.11 235);
}

@layer base {
  * { border-color: var(--color-border); }
  html {
    font-family: var(--font-sans);
    font-feature-settings: "cv11","ss01","ss03";
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    color-scheme: light dark;
  }
  body { background: var(--color-background); color: var(--color-foreground); }
  ::selection { background: var(--color-foreground); color: var(--color-background); }
  :focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes caret-blink { 0%,60% { opacity: 1 } 60.01%,100% { opacity: 0 } }
@keyframes marquee { from { transform: translateX(0) } to { transform: translateX(-50%) } }

@utility animate-entry { animation: fade-in-up 700ms var(--ease-out-expo) both; }
@utility caret { display: inline-block; width: 0.4rem; height: 1rem; background: currentColor; vertical-align: -0.15rem; animation: caret-blink 1.1s steps(1) infinite; }
@utility marquee-track { animation: marquee 40s linear infinite; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
```

---

## 18. `layout.tsx` — Root Shell

```tsx
import "./globals.css";
import { ThemeProvider } from "next-themes";

const noFlash = `
(function(){try{
  var t=localStorage.getItem('theme');
  var m=window.matchMedia('(prefers-color-scheme: dark)').matches;
  if(t==='dark'||((!t||t==='system')&&m))document.documentElement.classList.add('dark');
}catch(e){}})();
`;

export const metadata = {
  title: "Ibex Harness — The control plane for AI agents in production",
  description:
    "Open-source OpenAI-compatible proxy for agent fleets. Tenant auth, per-org limits, memory-ready request path, and observability — at the proxy.",
  metadataBase: new URL("https://ibexharness.com"),
  openGraph: { type: "website", siteName: "Ibex Harness" },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: noFlash }} /></head>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange={false}>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

---

## 19. Dependency List

```text
next@15  react@19  react-dom@19
tailwindcss@4  @tailwindcss/vite@4  (or PostCSS plugin for Next)
next-themes
framer-motion
lucide-react
@radix-ui/react-*   (via shadcn)
class-variance-authority  clsx  tailwind-merge
shiki
fumadocs-ui  fumadocs-mdx
@fontsource/instrument-serif
@fontsource-variable/inter
@fontsource-variable/jetbrains-mono
cmdk
recharts
```

Install shadcn primitives one at a time (`button`, `dropdown-menu`, `tabs`, `dialog`, `tooltip`, `toast`) rather than bulk — every one gets its tokens overridden.

---

## 20. What NOT to Ship

- ❌ Purple/indigo gradients, glassmorphism, neon glows, `backdrop-blur` on cards.
- ❌ "Trusted by" logo strips with fake companies.
- ❌ Rotating word animations in the H1.
- ❌ Dark mode that is just inverted light mode.
- ❌ Shadows on layout containers.
- ❌ Emoji in UI copy.
- ❌ Any hex literal in a component file.
- ❌ Framer Motion `whileHover={{ scale: 1.05 }}` on cards. Static, please.
- ❌ Full-page scroll-jack. Marquee only, and it pauses on hover.

---

## 21. Definition of Done

- [ ] Landing renders without CLS in both themes.
- [ ] Theme toggle: System/Light/Dark cycles; no white flash on dark reload; system change reflected live.
- [ ] All sections use `<SectionShell §="0X" label="…" meta="…" />`.
- [ ] Terminal card cycles tabs; respects reduced motion.
- [ ] Request-path node dot animates; pauses on hover.
- [ ] Benchmarks numbers count up once on in-view; tabular nums.
- [ ] Header GitHub star count live (ISR 1h), status dot live.
- [ ] Docs, blog, changelog, benchmarks routes all built and themed identically.
- [ ] Lighthouse ≥ 98 across the board on landing.
- [ ] axe-core: 0 violations.
- [ ] `og:image` renders for `/`, `/blog/[slug]`, `/changelog`, `/docs/…`.

---

*Hand this file to Cursor. Every value is a token; every section is a component; every motion is spec'd. Build it once, ship it quiet, let the type do the talking.*
