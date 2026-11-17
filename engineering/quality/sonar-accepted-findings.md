# Accepted static-analysis findings

Findings that are **accepted rather than fixed**, with the reason each is not actionable. This file exists so that
"accepted" is checkable by the next person instead of being inferred from an empty issue list.

## The rule

A finding is closed in exactly one of two ways:

1. **Fixed** — the code changes.
2. **Accepted here** — a written justification records why it is not actionable.

A finding that cannot be fixed without changing an artefact the repository must not change is accepted here and marked
as accepted in SonarQube. It is **never** suppressed inline: an inline suppression hides the finding from the next
reader and from the next scanner run, which defeats the purpose of this record. If a finding below is later fixed or
the reason stops holding, delete its row and say so in the change that removes it.

---

## `plsql:S1192` — duplicated string literal in migration SQL (15 open findings)

The rule asks that a repeated string literal be replaced by a named constant. In these files that remedy either does
not exist in the language context or would require rewriting an artefact that must not change. Two sub-classes:

### 1. Declarative DDL/DML has no constant mechanism

`infra/migrations/postgres/000004_rls.up.sql:7` repeats `'app.current_org_id'` across `CREATE POLICY` statements, and
`infra/scripts/seed_dev.sql:18,22,27` repeats values across `INSERT … VALUES`. Outside a `BEGIN … END` block there is
no `DECLARE`, no variable, no constant: the literal is the only way to write it. The rule's remedy does not exist in
this language context.

The same is true of DDL that happens to sit inside a `DO` block (an enum label in `CREATE TYPE` cannot be a variable)
and of `LANGUAGE sql` function bodies, which have no `DECLARE` section at all.

### 2. Applied migrations are immutable

These findings sit inside PL/pgSQL bodies that do have a `DECLARE` section, so a `CONSTANT` declaration **is**
possible. They are still not fixed: these files are applied migrations. Rewriting one changes the artefact every
environment has already run, and the migration set is forward-only by decision — ADR-0005 §4 ("No automated `down`;
use expand-contract and forward-only migrations"), restated in `engineering/DEPLOYMENT.md` §7.2, ADR-0097 §9, and
ADR-0098 §6. Satisfying a style rule is not a reason to rewrite schema history.

How strongly that rule binds depends on the migration version, and for the released range the difference is mechanical
rather than conventional:

- **At or below `000039`** (the last version in release v0.1.9) immutability is enforced by a test.
  `infra/migrations/postgres/testdata/released/v0.1.9.sha256` pins the SHA-256 digest of all 78 files (39 migrations, up
  and down), and `TestUnit_ReleasedMigrationSetImmutable` in
  `infra/migrations/postgres/migrate_released_set_test.go` fails when a pinned file is edited, removed, or renumbered.
  The test runs in `db-migrate-smoke`, which gates through `ci-gate-go`. Editing a migration in this range is a red
  build, not a review conversation.
- **Above `000039`** there is no checksum pin. Those files rest on ADR-0005 §4 and review alone: forward-only by
  decision, with nothing mechanical preventing an edit.

That distinction does not strengthen the case for this sub-class's findings, and it would be misleading to imply it
does. Every sub-class 2 finding (rows 1, 2, 4, and 6) is above `000039`, so the reason for leaving each of them alone is
ADR-0005 §4 and review, not the pin. The three findings at or below the boundary (rows 10, 11, and 15) are sub-class 1:
they are immutable *and* their remedy does not exist in the language context.

### Finding list

Line and literal verified with `sed -n` against the working tree. "Reported" is the duplicate count SonarQube
reports; "Seen" is the occurrence count measured in the file.

| # | File:line | Literal | Reported | Seen | Sub-class | Context |
|---|---|---|---|---|---|---|
| 1 | `000076_retention_sweep.up.sql:60` | `'invalid_parameter_value'` | 6x | 6 | 2 | `RAISE … USING ERRCODE =` in a PL/pgSQL function with `DECLARE` |
| 2 | `000076_retention_sweep.up.sql:71` | `'[scrubbed]'` | 4x | 4 | 2 | `UPDATE … SET exception_message/traceback`; 4 occurrences across 3 lines |
| 3 | `000074_memory_lifecycle_erasure_state.up.sql:30` | `'pending'` | 3x | 3 | 1 | top-level `ALTER TABLE … DEFAULT`, not a function body |
| 4 | `000069_bootstrap_definers.up.sql:181` | `'active'` | 7x | 7 | 2 | `VALUES (…)` inside a PL/pgSQL bootstrap function with `DECLARE` |
| 5 | `000069_bootstrap_definers.up.sql:257` | `'owner'` | 3x | 3 | 1 | inside a `LANGUAGE sql` body — no `DECLARE` section |
| 6 | `000064_service_role_model.up.sql:48` | `'ibex_worker'` | 4x | 4 | 2 | `IF NOT EXISTS (… rolname = …)` inside a `DO` block with `DECLARE` |
| 7 | `000046_budget_reservations.up.sql:16` | `'claimed'` | 5x | 5 | 1 | `CHECK (state IN (…))` in a top-level `CREATE TABLE` |
| 8 | `000046_budget_reservations.up.sql:16` | `'finalized'` | 3x | 3 | 1 | second finding on the same line, same `CHECK` list |
| 9 | `000043_idempotency_ledger.up.sql:8` | `'finalized'` | 3x | 3 | 1 | `CHECK (state IN (…))` in a top-level `CREATE TABLE` |
| 10 | `000020_memory_conflict_escalation_status_enum.up.sql:9` | `'pending'` | 3x | 3 | 1 | enum label in `CREATE TYPE` inside a `DO` block; DDL cannot take a variable |
| 11 | `000019_create_memory_conflict_escalations.up.sql:13` | `'pending'` | 3x | 3 | 1 | `DEFAULT` in a top-level `CREATE TABLE` |
| 12 | `infra/scripts/seed_dev.sql:18` | `'00000000-0000-0000-0000-000000000001'` | 6x | 6 | 1 | dev org UUID in `INSERT … VALUES` |
| 13 | `infra/scripts/seed_dev.sql:22` | `'active'` | 3x | 3 | 1 | `INSERT … VALUES` |
| 14 | `infra/scripts/seed_dev.sql:27` | `'00000000-0000-0000-0000-000000000002'` | 3x | 3 | 1 | dev user UUID in `INSERT … VALUES` |
| 15 | `000004_rls.up.sql:7` | `'app.current_org_id'` | 4x | 4 | 1 | `current_setting(…)` inside `CREATE POLICY … USING` |

Notes on the list:

- Every file and line above resolves to the literal shown. No stale line numbers were found.
- Row 9: the `CHECK` list also contains `'claimed'`, but it occurs only twice in that file, so the 3x finding is
  `'finalized'` (also used in the two-branch `CHECK` at lines 16–17).
- Rows 3, 5, 7, 8, 9, 10, 11 are **not** inside a PL/pgSQL body that could hold a `CONSTANT`, despite living in
  migrations that also contain function bodies. They are sub-class 1 by mechanism, not sub-class 2.
- Row 5 is inside a function, but a `LANGUAGE sql` body has no `DECLARE`; hoisting `'owner'` would need a
  `LANGUAGE plpgsql` rewrite, which is a behaviour change, not a constant extraction.

### Which constraint applies to which finding

The released-set pin stops at `000039`, so the 15 findings do not all rest on the same rule. The split:

| Constraint | Rows | Count |
|---|---|---|
| Pinned by `v0.1.9.sha256` — version ≤ 39 | 10, 11, 15 | 3 |
| ADR-0005 §4 and review only — version > 39 | 1–9 | 9 |
| Neither: not a migration | 12, 13, 14 | 3 |

Rows 10, 11, and 15 are the only ones the pin protects, and each is sub-class 1, so the pin is not what carries them.
Rows 1–9 are applied migrations that the pin does not cover: of those, rows 1, 2, 4, and 6 rely on immutability
(sub-class 2) and therefore on ADR-0005 §4 plus review; rows 3, 5, 7, 8, and 9 are sub-class 1 and do not rely on it.
Rows 12–14 live in `infra/scripts/seed_dev.sql`, a development seed script, which neither the pin nor the forward-only
rule governs; they are accepted on the sub-class 1 ground alone.

---

## Residual risk

- Immutability is mechanical only up to `000039`. Above that boundary the forward-only rule is still enforced by
  review, not by a test, and the four sub-class 2 findings (rows 1, 2, 4, 6) sit in that unpinned range. Pinning a
  newer released tag is what would extend the guarantee to them.
- 11 of the 15 findings are sub-class 1 and will never be fixable in place. A future squash or baseline reset is the
  only event that would make them fixable.

## Re-audit trigger

Revisit this record if migrations stop being immutable (for example a squash or a baseline reset), or if Sonar's
profile stops flagging `S1192` for SQL. In the first case rows 1, 2, 4, and 6 become fixable with a `CONSTANT` and the
remaining rows should be re-checked against the rewritten files; in the second the whole section can be closed.
