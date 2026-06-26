# Public docs site (Fumadocs)

Next.js + Fumadocs application for [docs.ibexharness.com](https://docs.ibexharness.com).

| Path | Purpose |
| --- | --- |
| `content/docs/` | Public MDX pages (created in D.2.1+) |
| `src/` | App Router, components, layout (D.2.1+) |

Engineering documentation (ADRs, roadmap, audits) lives in the parent [`docs/`](../) tree — not in this app.

## Run

From repo root:

```bash
pnpm install
pnpm docs:dev          # content authoring — http://localhost:3000
```

Open `http://localhost:3000` (redirects to introduction).

## Performance

**Do not judge navigation speed on `pnpm docs:dev`.** Dev mode compiles each MDX page on first visit (~200 pages with Shiki highlighting). That can take 5–30 seconds per page with no console output — this is normal for `next dev`, not a production bug.

For realistic navigation speed (sub-second between pages):

```bash
pnpm docs:build:clean
pnpm docs:start
```

Then browse `http://localhost:3000`. All 276 routes are pre-rendered at build time (`force-static`).

### Windows tips

- Stop stale servers before rebuilding: `pnpm --filter docs stop:next`
- Prefer `pnpm docs:dev:clean` or `pnpm docs:build:clean` over raw `next` commands
- Never run `dev`, `build`, and `start` concurrently on the same port
- **Wait for build to fully exit** before `pnpm start` — the last phases (`Collecting build traces`, `Finishing writing to cache`) can take 1–5 minutes with no output on Windows
- If cache write appears stuck, try `pnpm --filter docs build:fast` (disables webpack disk cache)
- Add a Windows Defender exclusion for `docs/app/.next` if builds are consistently slow

### Build phases (what to expect)

```text
[MDX] updated map file                    ~30ms
Creating an optimized production build    45–90s (silent)
Linting and checking validity of types
Generating static pages (276)             progress shown
Collecting build traces                   30s–3min (silent)
Finishing writing to cache                1–5min (silent on Windows)
```

`pnpm build` prints this summary at startup. Do not open a second terminal with `pnpm start` until you see the shell prompt return.

### After MDX / Mermaid changes

Mermaid ASCII is baked in at build time. Always run `pnpm docs:build:clean` before checking diagram output — restarting `docs:dev` alone will not fix already-compiled pages.

## Build

```bash
pnpm docs:build        # from repo root
pnpm docs:build:clean  # stop stale processes, clean .next, then build
```

See [Phase 1.5 roadmap](../roadmap/phase-1-5-docs-site/README.md) and [ADR-0023](../adr/ADR-0023-docs-site-architecture.md).
