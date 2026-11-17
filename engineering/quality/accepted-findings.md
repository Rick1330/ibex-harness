# Accepted static-analysis findings

Findings that are **not fixed outright** — suppressed inline at the call site, or accepted — with the reason each is not
a defect to correct. This file exists so that a disposition is checkable by the next person instead of being inferred
from an empty issue list.

## The rule

A finding is closed in exactly one of three ways:

1. **Fixed** — the code changes.
2. **Suppressed inline** — a false positive is narrowed to one rule at one call site, with the rule id and the reason
   in a `nosemgrep` comment next to the code, and the reasoning recorded here so the suppression stays reviewable.
   `engineering/agent-playbook.md` §6.1 requires the narrowest scope that covers the true positive, never whole-file
   or whole-rule.
3. **Accepted here** — a written justification records why it is not actionable, and the finding stays visible in the
   scanner.

A finding that cannot be fixed without changing an artefact the repository must not change is accepted here and marked
as accepted in SonarQube. It is **never** suppressed inline: an inline suppression hides the finding from the next
reader and from the next scanner run, which defeats the purpose of this record. The Codacy false positives below are
the other case: each is a single rule at a single call site, the reason sits next to the code, and the alternative —
Codacy can only exclude a whole file — was rejected because it would hide every other line of the file. If a finding
below is later fixed or the reason stops holding, delete its row and say so in the change that removes it.

---

## Disposition summary

| Tool | Findings | Disposition |
|---|---|---|
| SonarQube | 15 | Accepted — see `plsql:S1192` below |
| Codacy (Opengrep and Pylint) | 42 | 1 fixed, 41 suppressed inline at the call site — see "Codacy `Error` findings" below |

The Codacy set closes as **1 fixed** and **41 suppressed inline**, which accounts for all 42 findings.
Each suppression names one rule at one call site and carries its reason in the comment; the reason for
choosing that form over a file exclusion is recorded in that section.

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

---

## Codacy `Error` findings (42 findings: 1 fixed, 41 suppressed inline)

Codacy reports 42 `Error`-severity findings on `main`. Grouped by rule:

| Rule | Tool | Findings |
|---|---|---|
| `Semgrep_go_sql_rule-concat-sqli` | Opengrep | 39 |
| `Semgrep_python.django.security.injection.raw-html-format.raw-html-format` | Opengrep | 1 |
| `Semgrep_codacy.bash.security.hard-coded-password` | Opengrep | 1 |
| `PyLintPython3_E1120` | Pylint | 1 |

| Disposition | Findings | Files | Mechanism |
|---|---|---|---|
| Fixed | 1 | 1 | rule-scoped `# pylint: disable` at the call site |
| Suppressed inline | 41 | 21 | `// nosemgrep: <rule>` at the call site, reason inline |
| **Total** | **42** | | |

### Why the suppression is inline rather than by file

Codacy's `.codacy.yml` can only ignore whole files or globs, not a single finding. Excluding the 17 `_test.go` files
that carry the 37 fixture findings would also hide every *other* Opengrep finding in those files, and excluding
`store.go`, `ledger.go`, `budget.py`, or `pgcapability.sh` would do the same to production code.
`engineering/agent-playbook.md` §6.1 requires a suppression to be "the narrowest scope that covers the true positive …
**never whole-file or whole-rule**. A blanket disable is itself a finding." Each of the 41 findings is therefore
suppressed at its call site: one rule id, one reason, on the flagged line or the line immediately above a multi-line
call. The rule id is the Semgrep id without the tool prefix (`go_sql_rule-concat-sqli`, not
`Semgrep_go_sql_rule-concat-sqli`), matching the form the Opengrep SSRF suppression in this repository already uses.

### Why `concat-sqli` fires on all 39 sites

`Semgrep_go_sql_rule-concat-sqli` fires on **every parameterised Go query whose bound argument is a computed value**.
Its sink is any call to `Exec`/`Query`/`QueryRow` and its sources include `fmt.Sprintf(...)`, string concatenation, and
`strings.Builder.String()`, so a value built with one of those and then passed as a `$n` argument is reported as if the
statement text carried it. **The statement itself is never inspected.** In all 39 cases the statement is a literal or a
test-authored constant with `$n` placeholders — in two fixtures a test-authored fragment from a local table is
concatenated into it — and the flagged value is a bound argument. Two findings carry a `fmt.Sprintf`-built payload
that is bound as `$8::jsonb`/`$5::interval`, not statement text. Keeping that explanation here is what makes the
suppression reviewable.

### Fixed: `services/mcp-memory/app/stdio_main.py:49` — Pylint `E1120`

Pylint reports "No value for argument `enforcer` in constructor call" on `McpServerWiring(...)`. This
is the documented false positive from `AGENTS.md`: both MCP services define a top-level `app.server`
module, and a repo-root analysis resolves `from app.server import McpServerWiring` to the *other*
service's wiring class, which takes `enforcer` and `registry`. This service's class takes `audit`,
`memory_client`, `agent_verifier`, and `rate_limiter`, and the call passes exactly those. Fixed with
the same rule-scoped, documented disable that `services/mcp-memory/app/descriptors.py:42` and
`services/mcp-operator/app/descriptors.py:52` already carry.

### Suppressed 1: `packages/evidenceoutbox/store.go:550` — `concat-sqli`

The flagged call is `tx.ExecContext(ctx, <statement>, rowID, w.OrgID, …, raw, digest, …)` in
`enqueueOutbox`. The statement is a backtick string literal containing `$1`–`$11`; every value is a
bound argument and nothing is concatenated into the SQL text. The taint path the rule follows is
inside the payload, not the query: `addProducerMetadata` (same file) builds the payload with
`fmt.Sprintf("%q", class)`, which taints the bytes returned by `marshalOutboxPayload`, and those
bytes are passed as the `$8::jsonb` argument.

What would change the answer: the payload bytes or any other value being formatted into the
statement text instead of bound, or the rule ceasing to treat a bound argument as a sink.

### Suppressed 2: `packages/idempotency/ledger.go:135` — `concat-sqli`

Same rule, same mechanism. The flagged call is
`tx.QueryRowContext(ctx, insertLedgerSQL, p.OrgID, p.AgentID, key, requestHash, fmt.Sprintf("%f seconds", …))`.
`insertLedgerSQL` is a package-level constant with `$1`–`$5` placeholders; the only rule source on the
line is the lease interval formatted with `fmt.Sprintf` and passed as the `$5::interval` argument.

Codacy reports this as a fourth non-test finding under the same rule. It is the same false positive,
so it is suppressed at the call site like the rest.

What would change the answer: the lease interval, the key, or the request hash being formatted into
the statement text instead of bound.

### Suppressed 3: `services/context/app/budget.py:121` — `raw-html-format`

The flagged line is `return f'<ibex_memory nonce="{nonce}">'` in `_memory_open_tag_for_estimate`. Its
only caller is `_framing_sentence_for_estimate`, whose only caller is `_framing_overhead_text`, which
is reached from `BudgetCalculator.calculate` with `nonce = representative_nonce(request.nonce_bytes)`.
`representative_nonce` (line 89) returns `"A" * length` with `length` derived from `nonce_bytes`
clamped to `MAX_NONCE_BYTES`: a configuration integer, never request content. The string is a token
estimator's placeholder and is never served to a browser.

What would change the answer: a caller passing request-derived text as `nonce`, or this helper being
reused to build HTML that is actually rendered.

### Suppressed 4: `infra/scripts/lib/pgcapability.sh:68` — `hard-coded-password`

The flagged line is `local password="${3:-}"`, the empty default for the optional third argument of
`capability_dsn`. No literal credential is assigned: the value is either the caller's override or,
on the next branch, the output of `capability_password`. Every production caller
(`infra/scripts/*.sh`, `benchmarks/scripts/start_proxy_stack.sh`) passes two arguments; the third is
used only by `infra/tests/pgcapability/test_pgcapability.py` to test percent-encoding of a hostile
verifier.

The `nosemgrep` comment that already existed on line 71 suppresses the `capability_password` call on
line 72, not this assignment, so this finding needed its own comment. Both are present now: one
suppression per rule at one call site, not one comment covering the function.

What would change the answer: a literal password being assigned at this line, or the `${3:-}` override
becoming reachable from a production caller.

### Residual risk

- Each suppression is tied to the rule id string in its comment. If Opengrep renames a rule, the
  comment silently stops suppressing and the finding returns. That is the intended failure mode — it
  is visible, not silent — and the fix is to update the id here and at the call sites together.
- No file is excluded for Opengrep, so a *new* finding in any of these 21 files is still reported.
  That is the property a file-level exclude would have destroyed.
- Whether Codacy honours `nosemgrep` in-source is confirmed by the next Codacy analysis on the pull
  request, not by this record. If a finding persists with the correct rule id in place, the fallback is
  to retain that finding with a written justification (as this section did before) rather than re-add a
  file exclusion.

### Re-audit trigger

Revisit this record if Opengrep's `concat-sqli` rule stops treating bound arguments as sinks, if
`representative_nonce` stops being the only source of the framing nonce, if `capability_dsn` gains a
caller that passes a literal password, or if any of the 21 suppressed sites is edited to build SQL
text from a value instead of binding it.
