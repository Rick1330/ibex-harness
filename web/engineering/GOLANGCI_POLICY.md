# golangci-lint policy (Wave 1 / MF-002)

Three configs / invocations keep import boundaries, base quality, and
complexity gates from interfering with each other.

## Architecture import boundaries (no grandfathering)

Config: `.golangci.depguard.yml`

`depguard` rule `packages-no-services` blocks `packages/**` from importing
`github.com/Rick1330/ibex-harness/services/**`.

Runs **without** `issues.new` / `new-from-rev`, so existing or new violations
always fail CI.

## Base linters (full tree, no whole-files)

Config: `.golangci.yml`

`govet`, `staticcheck`, `revive`, and `errcheck` run on the full packages /
services scope. No `issues.whole-files` — line-level findings only for the
usual static analysis suite.

## Complexity (new/changed files only, whole-files scoped here)

Config: `.golangci.complexity.yml` (`funlen` ≤40 lines / ≤30 statements,
`gocognit` ≤10)

- `issues.new: true` with `new-from-rev: origin/main` suppresses **unchanged**
  production hotspots.
- `issues.whole-files: true` re-evaluates the **entire** file when any part of
  it changes, so body-only edits that worsen complexity still fail.
  Scoped to this config only so touching a legacy file does not re-surface
  grandfathered `revive`/`errcheck`/`staticcheck` noise.
  (`whole-files` requires `new-from-rev`; incompatible with
  `new-from-merge-base` in golangci-lint v2.8.)
- `_test.go` files are excluded from both complexity linters.
- `make lint-go` and CI refresh `origin/main` before this run
  (`infra/scripts/ensure-origin-main.sh` always fetches; fails only if the
  ref is still missing after a failed/offline fetch).
Local/CI entrypoint: `make lint-go` (or the `golangci-lint` workflow job).

## Removing grandfathered complexity

As Waves 2–4 shrink hotspots (MF-003, MF-016), new code in those areas must
meet limits immediately. Refactors that touch grandfathered functions should
shrink them below thresholds when practical.

## Proxy Postgres / `database/sql` (MF-001)

**Phase 1 rule** (always applied in `.cursor/rules/20-architecture-layering.mdc`):
the proxy must not own a `pgxpool.Pool` for identity; auth stays on gRPC.

**Current exception (MF-001):** `services/proxy/cmd/proxy/main.go` still opens
Postgres for **session and directive** stores (not identity). This is a
documented deviation from the Phase 1 “no proxy DB” wording until an ADR or
migration removes it. A `depguard` deny on `database/sql` under `services/proxy`
is **deferred** until that decision.
