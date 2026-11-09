---
title: "ADR-0098: Unforgeable RLS tenancy and the service role model"
description: "Architecture decision record 0098: replace the forgeable app.is_service_account GUC with a current_user predicate, remove BYPASSRLS from ibex_service, split service capabilities into dedicated logins, and route the five cross-tenant reads through SECURITY DEFINER functions."
adrId: "0098"
status: "Accepted"
date: "2026-11-09"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-09" id="0098"}
::

# ADR-0098: Unforgeable RLS tenancy and the service role model

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

**3. Four capability roles replace the single owner login.** They are created with no password and stay inert until
`migrate provision` sets one from a dedicated environment variable.

| Role | Login | Attributes | Memberships | Purpose |
|---|---|---|---|---|
| `ibex_runtime` | yes | NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT | `ibex_app` | API/proxy/auth request paths; sets role `ibex_app` for tenant queries |
| `ibex_worker` | yes | same | `ibex_app`, `ibex_purge` | Celery work; sets role `ibex_app` for tenant work and `ibex_purge` for the deletion saga |
| `ibex_bootstrap` | yes | same | `ibex_service` | one-shot schema/tenant bootstrap |
| `ibex_purge` | no | NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT | none | org-deletion purge; reachable only through `ibex_worker` |

`ibex` remains the owner login and the only `rolsuper`/`rolbypassrls` role. It is also a member of `ibex_service` and
`ibex_app` so migrations and operator repair can assume either identity. Forbidden memberships are revoked explicitly,
not left to absence.

**4. The org purge uses `ibex_purge`, not `ibex_service`, and stays org-GUC-scoped.** Every saga statement filters a
known `org_id` (`_PG_PRE_CASCADE`, `_CASCADE_STATEMENTS`, `_claim_job`, receipts, finalize). `ibex_purge` gets only the
verbs and columns those statements use. It can read `org_id` where a policy or `RETURNING` needs it; it cannot read
memory content, provider credentials, token hashes, TOTP secrets, or hold reasons. A `BEFORE DELETE` trigger on
`legal_holds` raises unless `OLD.cleared_at IS NOT NULL`, so an active hold cannot be deleted even by a statement that
forgets the predicate.

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

**6. The migration is one unit: `000063` → `000064` → `000065`.** `000063` rewrites the three helpers, alters the 13
inline policies in place (no `DROP POLICY`/`CREATE POLICY` churn), grants helper execution, and terminates the
attribute. `000064` creates the roles, memberships, purge grants, and the legal-holds trigger. `000065` creates the
readers and the column privileges their definer bodies need. Down files exist for development and rollback; production
is forward-only.

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

## Consequences

**What changes**

- The old GUCs are inert. No policy or function body mentions `app.is_service_account` or `app.current_user_id`.
- `ibex_service` no longer bypasses RLS. Its existing definer functions work because they run as the owner and the
  policies admit that identity.
- Cross-tenant reads are explicit function calls with a named caller, not an ambient session flag.
- The purge has its own least-privilege identity, and an active legal hold is protected in the database, not only by the
  saga's `WHERE` clause.
- `migrate provision` is the only writer of the three login passwords; it refuses a missing secret, a NUL byte, or a
  secret equal to `POSTGRES_PASSWORD`, and it asserts `rolsuper = false`, `rolbypassrls = false`, `rolcanlogin = true`
  before commit. It sends a pre-computed SCRAM-SHA-256 verifier (4096 iterations, random 16-byte salt), never the
  plaintext, so a failing statement cannot put the password in the server log.

**What does not change yet**

- The services still run as `ibex` in the supported profile, so their current GUC writes are inert but harmless. PR-2..4
  remove them and pin roles.
- `ibex_bootstrap` is a member of `ibex_service`. Under the new policies that is a **full cross-tenant capability**:
  `SET ROLE ibex_service` makes `current_user = 'ibex_service'`, so every tenant policy admits its reads and writes
  without `BYPASSRLS`. This is deliberate for a one-shot, no-listener bootstrap login whose only job is to create the
  first org/user and repair schema state; it is provisioned only for that job and has no request path. It is **not** a
  least-privilege tenant identity, and its safety rests on credential handling and process lifetime, not on table
  grants. PR-3 must either narrow it (for example, replace the bootstrap statements with a reviewed `SECURITY DEFINER`
  path and revoke the membership after the one-shot run) or record the bootstrap trust boundary explicitly. Leaving it
  as an ambient service login with no listener is acceptable only while the credential is operator-controlled and the
  process exits.
- No compose file, DSN, or deployment manifest changes in this unit. The new logins are inert until provisioned.
- No ledger row is promoted. The runtime claim stays where the status ledger records it.

**Costs and limits**

- `ALTER POLICY` is catalog-only (no table rewrite, no backfill) but takes an `ACCESS EXCLUSIVE` lock on each target
  table for the duration of that statement (milliseconds). On a hot table this is a short write barrier; schedule the
  migration, do not assume it is lock-free. `CREATE OR REPLACE FUNCTION` and `ALTER ROLE` are similarly brief catalog
  operations; `CREATE TRIGGER` takes `SHARE ROW EXCLUSIVE` on `legal_holds`.
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
- `infra/migrations/postgres/cmd/migrate/provision.go` and `provision_test.go`
- `infra/migrations/postgres/migrate_unforgeable_tenancy_integration_test.go`
- [`31-v1-release-plan-2026-11-09.md`](../architecture-v2/31-v1-release-plan-2026-11-09.md), P0-06 and W8
- PostgreSQL row security and custom-option semantics: the server assigns `current_user`; two-part GUCs are settable by
  any role.
