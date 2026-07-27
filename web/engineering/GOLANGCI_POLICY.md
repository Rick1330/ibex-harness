# golangci-lint policy (Wave 1 / MF-002)

## Architecture import boundaries (no grandfathering)

`depguard` rule `packages-no-services` blocks `packages/**` from importing
`github.com/Rick1330/ibex-harness/services/**`.

This check runs via `.golangci.depguard.yml` **without** `issues.new` /
`new-from-merge-base`, so existing or new violations always fail CI.
Local/CI entrypoint: `make lint-go` (or the `golangci-lint` workflow job).

## Complexity (new/changed files only)

`funlen` (≤40 lines, ≤30 statements) and `gocognit` (≤10) live in `.golangci.yml`:

- `issues.new: true` with `new-from-merge-base: main` suppresses **unchanged**
  production hotspots.
- `issues.whole-files: true` re-evaluates the **entire** file when any part of
  it changes, so body-only edits that worsen complexity still fail.
- `_test.go` files are excluded from both linters (table-driven tests).

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
