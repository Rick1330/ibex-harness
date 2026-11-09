---
title: "ADR-0098: Remove the forgeable service-account bypass"
description: "Architecture decision record 0098: replace the forgeable app.is_service_account GUC with a current_user predicate, remove BYPASSRLS from ibex_service, split service capabilities into dedicated logins, and route the five cross-tenant reads through SECURITY DEFINER functions. The tenant selector remains a transaction-local GUC."
adrId: "0098"
status: "Accepted"
date: "2026-11-09"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-09" id="0098"}
::

# ADR-0098: Remove the forgeable service-account bypass

- **Status:** Accepted
- **Date:** 2026-11-09
- **Authors:** Elshaday Mengesha (@Rick1330)
- **Gates:** P0-06 (RLS inert / bypass survives pinning), and the tenancy half of the v1.0 definition of done
- **Depends on:** [ADR-0097](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0097-v1-supported-profile.md)
  (the supported profile and its attack surface)
- **Supersedes:** the `app.is_service_account` evidence/tenant bypass introduced by migrations `000004`, `000006`,
  `000007`, `000009`, `000024`–`000029`, `000032`, `000033`, `000035` and `000036`, and the BYPASSRLS attribute granted to
  `ibex_service` in `000036`

## Context

P0-06 records that row-level security is inert on the paths that matter: `api`, `mcp-operator` and `memory` pin
`ibex_app` and clear the service bypass, but `auth`, `worker`, `relay` and the Go `packages/session` still set
`app.is_service_account` without a role pin. The plan called that "half real" tenancy.

The deeper problem is the mechanism, not the number of call sites. Since PostgreSQL 9.2, any role can `SET` a custom
two-part GUC, and `set_config('app.is_service_account', 'true', true)` is a custom GUC. A policy of the form

```sql
current_setting('app.is_service_account', true) = 'true'
```

is therefore not an authorization boundary. It is a flag the tenant role can set for itself. This was measured, not
assumed: in the migration test database a fresh `NOLOGIN NOBYPASSRLS` role set `app.current_org_id` and read through a
policy that trusted it. An attacker who can run one statement as `ibex_app` can read every tenant.

`ibex_service` carried the same weakness from the other direction. It was created `BYPASSRLS` in `000036`, so the
attribute, not a policy, authorized every cross-tenant evidence reader. Removing the GUC alone would have left that
attribute as the real boundary, and the attribute cannot be audited per query.

The repository also had two dead or over-broad predicates. `app.current_user_id` appeared only in the `users` and
`agents` policies; no service ever wrote it. `idempotency_ledger_isolation` was org-only, so a future `SECURITY DEFINER`
reader could not see it.

## Decision

**1. The tenant predicate becomes `current_user = 'ibex_service' OR <org equality>`.** `current_user` is set by the
server from the authenticated identity or from the owner of a `SECURITY DEFINER` function; a client cannot forge it.
The three helper functions (`rls_org_visible`, `rls_evidence_visible`, `rls_privacy_visible`) keep `SECURITY INVOKER`
explicitly. Inside a definer `current_user` is the owner, so a definer helper would make every policy pass for every
caller.

**2. `ALTER ROLE ibex_service NOBYPASSRLS` runs as the last statement of the same migration**, after all policies trust
the new predicate. The attribute is replaced by an explicit, auditable policy branch. Existing `SECURITY DEFINER`
functions owned by `ibex_service` keep working because they execute with `current_user = 'ibex_service'`.

**3. Four capability roles replace the single owner login.** They are created with no password; the three logins also
start with `CONNECTION LIMIT 0`, so they stay inert regardless of `pg_hba` until `migrate provision` sets a SCRAM
verifier and clears the limit to `-1`.

| Role | Login | Attributes | Memberships | Purpose |
|---|---|---|---|---|
| `ibex_runtime` | yes | NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT CONNECTION LIMIT 0 | `ibex_app` | API/proxy/auth request paths; sets role `ibex_app` for tenant queries |
| `ibex_worker` | yes | same | `ibex_app`, `ibex_purge` | Celery work; sets role `ibex_app` for tenant work and `ibex_purge` for the deletion saga |
| `ibex_bootstrap` | yes | same | none | inert until PR-3 adds a narrow bootstrap definer; it does **not** hold the service identity |
| `ibex_purge` | no | NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT | none | org-deletion purge; reachable only through `ibex_worker` |

`ibex` remains the owner login and the only `rolsuper`/`rolbypassrls` role. It is also a member of `ibex_service` and
`ibex_app` so migrations and operator repair can assume either identity. `ibex_service` has exactly one member, `ibex`.
Forbidden memberships are revoked explicitly, not left to absence.

**4. The org purge uses `ibex_purge`, not `ibex_service`, and stays org-GUC-scoped.** Every saga statement filters a
known `org_id` (`_PG_PRE_CASCADE`, `_CASCADE_STATEMENTS`, `_claim_job`, receipts, finalize). `ibex_purge` gets only the
verbs and columns those statements use. It can read `org_id` where a policy or `RETURNING` needs it; it cannot read
memory content, provider credentials, token hashes, TOTP secrets, or hold reasons. A `BEFORE DELETE` trigger on
`legal_holds` raises for `ibex_purge` when `OLD.cleared_at IS NULL`, so the purge cannot delete an active hold even if
its statement forgets the predicate. `ibex_service` loses `DELETE` on `legal_holds`; the owner and the purge role are
the only delete paths.

**5. Five cross-tenant reads become `SECURITY DEFINER` functions owned by `ibex_service`, each granted to exactly one
caller.**

| Function | Call site | EXECUTE |
|---|---|---|
| `ibex_core.auth_find_token_by_prefix(text)` | `services/auth/internal/repository/tokens.go` | `ibex_runtime` |
| `ibex_core.rate_limit_overrides_snapshot()` | `packages/ratelimit/config_store.go` | `ibex_runtime` |
| `ibex_core.sessions_abandon_idle(timestamptz, int)` | `packages/session/abandon_idle.go` | `ibex_runtime` |
| `ibex_core.budget_reservations_expire_stale(interval, int)` | `services/worker/app/budget_ledger.py` | `ibex_worker` |
| `ibex_billing.active_periods()` | `services/worker/app/tasks/billing_reconcile.py` | `ibex_worker` |

Each has `SET search_path = <schema>, pg_temp`, no dynamic SQL, parameter validation, a bounded `LIMIT`, and a return
shape copied from the call site rather than invented. `REVOKE ALL ... FROM PUBLIC` precedes the single grant. The
tenant role gets none of them.

**6. The migration is one unit: `000063` → `000064` → `000065` → `000066`.** `000063` rewrites the three helpers,
alters the 13 inline policies in place (no `DROP POLICY`/`CREATE POLICY` churn), grants helper execution, and terminates
the attribute. `000064` creates the roles, memberships, purge grants, and the legal-holds trigger. `000065` creates the
readers and the column privileges their definer bodies need. `000066` adds the missing `tokens.prefix` index
(`CREATE INDEX CONCURRENTLY`, one statement per file). Down files exist for development and rollback; production is
forward-only.

**7. Ordering invariant: policies and roles land before any login is swapped.** PR-1 (this unit) changes the database
only. PR-2..PR-4 pin `ibex_app` in `auth`, `worker`, and the Go packages, and move the five reads to the readers. Only
after a service pins its role may its DSN change to a capability login. A login swap before the pin would run the
service as `ibex` (owner, superuser) and bypass RLS silently, which is worse than the half-state it replaces.

## The measured fact

A custom GUC is not an authorization boundary. The following is valid for any role that can connect:

```sql
SET app.is_service_account = 'true';
SELECT current_setting('app.is_service_account', true); -- 'true'
```

`current_user`, by contrast, is assigned by the server and can only become `ibex_service` through a membership
(`SET ROLE`) or through the owner of a `SECURITY DEFINER` function. Both are catalog-visible and reviewable.

## What this does not make unforgeable

The tenant **selector** is still `app.current_org_id`, a transaction-local GUC set by the trusted application layer. It
is not signed and not derived from an authenticated principal by the database. A caller that can run arbitrary SQL as
`ibex_app` can set the org GUC to another tenant and read that tenant's rows, exactly as before this change. RLS here is
a backstop for code that runs as `ibex_app`; it is **not** a barrier against arbitrary SQL by the `ibex_app` role.

What changed is the **service identity**: `app.is_service_account` was a flag the caller could set, and
`current_user = 'ibex_service'` is a role the server assigns. That removes the ambient cross-tenant bypass from every
tenant path. It does not make the tenant selector unforgeable.

The two future options are (a) per-tenant database roles, so the server rather than a GUC chooses the tenant, or (b) a
`SECURITY DEFINER` entry point that validates a signed tenant claim before it sets the selector. This PR does neither;
both are larger changes that the supported profile does not require yet.

## Consequences

**What changes**

- The old GUCs are inert. No policy or function body mentions `app.is_service_account` or `app.current_user_id`.
- `ibex_service` no longer bypasses RLS. Its existing definer functions work because they run as the owner and the
  policies admit that identity.
- Cross-tenant reads are explicit function calls with a named caller, not an ambient session flag.
- The purge has its own least-privilege identity, and an active legal hold is protected in the database, not only by the
  saga's `WHERE` clause.
- `migrate provision` is the only writer of the three login passwords; it requires three pairwise-distinct secrets, each
  different from `POSTGRES_PASSWORD`, and it sends a pre-computed SCRAM-SHA-256 verifier (4096 iterations, random
  16-byte salt), never the plaintext, so a failing statement cannot put the password in the server log. In the same
  statement it clears `CONNECTION LIMIT`; it then asserts `rolsuper`, `rolbypassrls`, `rolcreatedb`, `rolcreaterole`,
  `rolinherit` are false, `rolcanlogin` is true, and `rolconnlimit = -1`.
- `privacy_audit_append` and `ibex_billing.clear_enforcement_budget_period_id` lose their `ibex_app` EXECUTE grants.
  The only `privacy_audit_append` caller is the worker purge path (which uses `ibex_purge`, and still has EXECUTE); the
  trigger function fires without an EXECUTE check. Both grants are restored in the down file.
- `ibex_purge`'s `org_deletion_jobs` and `deletion_store_receipts` grants are column-scoped to the saga's statements;
  `org_deletion_jobs` has no INSERT because the API creates the job as `ibex_app`.
- `000066` indexes `tokens.prefix` with `CREATE INDEX CONCURRENTLY`, and `auth_find_token_by_prefix` orders by
  `created_at DESC` so a duplicate prefix has a deterministic winner.

**What does not change yet**

- The services still run as `ibex` in the supported profile, so their current GUC writes are inert but harmless. PR-2..4
  remove them and pin roles.
- `ibex_bootstrap` is created `LOGIN` with `CONNECTION LIMIT 0` and **no membership**. It cannot connect before
  `provision`, and after `provision` it still has no service identity, no tenant-table grants, and no path to another
  org. PR-3 will add a narrow `SECURITY DEFINER` bootstrap function and grant exactly that; until then the role is
  intentionally unusable. This is why the service identity has exactly one member, `ibex`.
- No compose file, DSN, or deployment manifest changes in this unit. The new logins are inert until provisioned.
- No ledger row is promoted. The runtime claim stays where the status ledger records it.

**Costs and limits**

- `ALTER POLICY` is catalog-only (no table rewrite, no backfill) but takes an `ACCESS EXCLUSIVE` lock on each target
  table. Because the file is one transaction, the locks accumulate until `COMMIT`; the migration is short but it is a
  read+write barrier on the altered tables (including `tokens` and `organizations`). Run it in a low-traffic window and
  keep `lock_timeout`. Measured via `pg_locks`; `CREATE TRIGGER` takes `SHARE ROW EXCLUSIVE` on `legal_holds`.
- `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, so `000066` is deliberately one statement per file (the
  same pattern as `000059`). A failed build can leave an INVALID index; drop it and retry.
- The migration suite now creates and drops the four capability roles; `resetSchema` drops them before `ibex_app` so a
  rerun is idempotent.
- `ibex_service` needs column privileges on `tokens`, `organizations`, `rate_limit_overrides`, and `sessions` for the
  reader bodies. Those grants are column-scoped and live in `000065`, not in the tenant role.

## Residual risk: `ibex_purge`

`ibex_purge` is a cross-tenant deletion identity by design. Its residual risk is bounded but not zero:

- It can delete every tenant row the saga names, one org at a time, if a caller sets `app.current_org_id` to that org.
  The saga is the only caller and runs from the `maintenance` queue behind the legal-hold advisory lock; the trigger is
  the database-side backstop, not a substitute for the saga's authorization check.
- It can read `org_id` (and, for `memories`, `id` and `lifecycle_revision` for the outbox `RETURNING`) but not content,
  credentials, hashes, TOTP secrets, or hold reasons. The sealed integration test asserts each denial.
- It is not a member of `ibex_service`, so it cannot inherit the reader identity. It is reachable only from
  `ibex_worker` via `SET ROLE`.

A compromised `ibex_worker` credential can therefore still drive a deletion for an org it can name. That is the same
authority the worker already needed to run the saga; the change removes the ambient BYPASSRLS reach that made every
org readable, not the deletion authority itself.

## Recorded residual risks and non-goals

These are known and deliberately **not** fixed in this unit:

1. **The tenant selector is still a client-set GUC.** Per-tenant database roles or a definer that validates a signed
   tenant claim are the only true fixes; both are out of scope, and this PR does neither. A caller with arbitrary SQL as
   `ibex_app` can still set `app.current_org_id` and read another tenant.
2. **The supported profile still connects every service as the `ibex` superuser** until PR-4 swaps the DSNs. Until then
   RLS is inert for those services and this migration is defensive only. The ordering invariant in decision 7 is what
   keeps the swap from silently reintroducing that state.
3. **The legal hold is enforced by the saga and a row trigger, not by a database-wide invariant.** The saga checks the
   hold under an advisory lock and the `ibex_purge` trigger rejects an active-hold delete. A DB-level "no tenant row may
   be deleted while a hold is active" backstop is not built. `ibex_app` keeps `UPDATE`/`INSERT` on `legal_holds` because
   the API's hold endpoints need them.
4. **The three cross-tenant readers share the `ibex_runtime` login.** Splitting them onto separate logins (or moving the
   session sweep to the worker) is a PR-4 decision once Compose wires the logins; the function grants are already
   per-function, so the split is a credential and DSN change, not a rewrite.
5. **`down` restores the old bypass.** Production is forward-only. If a rollback is ever needed, the rollback unit is the
   whole wave (`000063`–`000066` plus the service pins), not an individual migration.

## Alternatives rejected

- **Keep the GUC and enforce it only in application code.** Rejected: the database is the last line of defense, and the
  measured fact shows the flag is client-writable.
- **Grant `ibex_purge` the table-level `SELECT` its policies evaluate and accept content readability.** Rejected:
  column-scoped `SELECT (org_id)` satisfies the policy (verified) without exposing content.
- **Grant the readers to `ibex_app` so any pin can call them.** Rejected: every login that can set role `ibex_app`
  would gain cross-tenant reads. Grant only to the login that needs the read.
- **Keep `ibex_service` BYPASSRLS and rely on role membership alone.** Rejected: BYPASSRLS is invisible per query and
  survives future policy mistakes; `current_user` is explicit and testable.

## References

- Migration `infra/migrations/postgres/000063_unforgeable_rls_role_term.{up,down}.sql`
- Migration `infra/migrations/postgres/000064_service_role_model.{up,down}.sql`
- Migration `infra/migrations/postgres/000065_privileged_tenant_readers.{up,down}.sql`
- Migration `infra/migrations/postgres/000066_token_prefix_index.{up,down}.sql`
- `infra/migrations/postgres/provision.go` and `provision_test.go`
- `infra/migrations/postgres/migrate_unforgeable_tenancy_integration_test.go`
- [`31-v1-release-plan-2026-11-09.md`](../architecture-v2/31-v1-release-plan-2026-11-09.md), P0-06 and W8
- PostgreSQL row security and custom-option semantics: the server assigns `current_user`; two-part GUCs are settable by
  any role.
