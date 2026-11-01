# Loop State — IBEX Harness

Last run: 2026-11-01 (manual session with shell access)

Level: L1 report-only. No auto-fix. No `loop-pause-all` flag present.

## High Priority (loop is acting or waiting on human)

1. **G0 contract review/expiry is 2026-11-10 — 9 days out.**
   - Evidence: `engineering/architecture-v2/00-status-and-evidence.md` line 3 and every row's Review column.
   - Why: five `accepted` contract shapes and most `provisional` rows carry that expiry. Miss it and the ledger's own claim rule turns them `unknown`.
   - Action for human: book the owner review this week; execute by Nov 5 so the date is not the deadline.
   - Effort: ~30 min review, no code.

2. **L1 still cannot see CI results or issues.** No GitHub connector at L1 (LOOP.md §Connectors says L1 needs none).
   - Why: a triage loop that cannot see CI failures is blind to its primary input.
   - Action for human: grant a read-only GitHub MCP (CI status + issues, **read scope only**) or publish a status artifact the loop can read.
   - Effort: ~15 min human, no code.

3. **The console branch carries the truth reset in three commits; nothing is pushed.**
   - Evidence: `4399e2e5` (Nuxt console + core/platform tiers), `fbe49cc0` (ADR-0089 + docs + ledgers), and the loop-tooling commit. All are signed off; the working tree is clean apart from local `.codacy/` config.
   - Why: the branch was previously parked with zero commits and no recorded direction. ADR-0089 resolves the direction and the gates pass locally; the remaining step is a tracking issue and a PR.
   - Action for human: open the tracking issue, then push and open the PR. Do not merge before CI and the required checks are green.

## Watch List

- **Console freeze is active.** Core live ratio is 3/10. No new surface may be added until at least five core surfaces are live and every core surface has an owning contract (ADR-0089 §3).
- **Release manifest needs owner approval.** ADR-0089 §6 sets the direction, but `.github/workflows/**` and release-config changes require approval under `AGENTS.md` §10. Nothing was edited there.
- **Legacy console auth UI was deleted with the Next.js tree.** `services/console/src/lib/auth/*` and `services/console/src/components/auth/*` are gone as part of the rebuild. `services/auth/` is untouched and no auth behaviour changed. The PR body must record this against the `auth/` deny-list in `loop-constraints.md`.
- **Phase 4 gaps still open** (GAP-001, 002, 004, 006, 007, 009, 011). All are recorded with evidence and owners in the ledger; none is new this run. Monitor only.
- **Ledger console rows were rewritten** to the core/platform tier model and now cite ADR-0089 in all three places. Re-verify them on the next docs run.
- **Site rebuild (2026-10-24/25)** stays watch-only. Confirm the next `main` run of `site-deploy` plus `check:links`, `check:redirects`, and `check:claims` is green.
- **Claim-affecting open holes**: operator gateway PolicySnapshot evaluator unwired; relay `required_evidence=false` gate unresolved; chat acknowledgement not response-bound. Already documented — do not re-report as new.

## Recent Noise (ignored this run)

- `new findings/` at repo root — **gitignored** local audit scratch. Useful context, not repo state.
- `test-results/junit/ratelimit-hierarchical-integration.xml` — stale artifact from 2026-09-11. Not current evidence.
- Reflog churn of `fix(ci)` / `fix(scanner)` / `CodeScene` commits on already-merged branches — normal PR review iteration.
- Dependabot + CodeQL pin bumps — housekeeping, resolved on their branches.
- `services/dashboard` compatibility shell — known and intended (AGENTS.md §1.1).

## State Updates (remember next run)

- Branch: `feat/console-nuxt-rebuild`. ADR-0089 accepted 2026-11-01.
- Console surfaces: 10 core (3 live: Overview, Platform, Explore; 7 preview), 8 platform tier (all preview).
- Next live work, in order: Agents, Policies, Settings; then Sessions, Memories, Evidence. Do not wire platform-tier surfaces first, even when their read model is cheaper.
- Preview fixtures are legal under ADR-0089 §4: `org_demo_` identifiers, one enumerable registry, persistent banner, 0% live verdict, no import from a live path.
- Latest release in `CHANGELOG.md`: v0.1.9 (2026-10-04). Issue/PR numbers in flight: up to ~#1043.
- Invariants verified this run:
  - `ci-gate-web` present in `ci.yml`, `branch-protection-main.json`, and `check-required-ci-gates.sh`.
  - `site/app/data/ledger.ts`, the public status page, and `check:claims` still exist and now cite ADR-0089 for the console rows.
  - `services/console/shared/operator/surfaces.ts` is the single surface-status source; `check:surfaces` asserts README parity and tier placement.
- This remains loop run #1: `STATE.md` was empty and `loop-run-log.md` had no entries before it.
- No scheduler installed (LOOP.md §Scheduling not enabled) — runs are manual.

---

Run log: `loop-run-log.md`
