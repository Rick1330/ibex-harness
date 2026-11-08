# W3 — Tenancy and Erasure: plan and current state

**Status:** planning record. Slice 1 is implemented on `feat/w3-tenancy-erasure` (local, unpushed). P0-06 is
designed here and not implemented.

**Owner:** Elshaday Mengesha (@Rick1330). **Date:** 2026-11-08.

**Authority:** `27-v1-readiness-audit.md` §7 (wave definition and exit gate), `28-g0-review-record-2026-11-06.md`
(D9, GAP-001/006/007), ADR-0097 (profile), `00-status-and-evidence.md` (claim rule).

---

## 1. Exit gate (verbatim from the audit)

> Cross-tenant negative suite green in the selected profile **and** a seeded org deletion reaching `succeeded` with
> zero rows **and** a forget that erases content.

## 2. Findings this wave must close

| ID | Defect | Evidence |
|---|---|---|
| **P0-06** | RLS is inert: every service connects as the superuser `ibex`, and `set_service_org` sets `app.is_service_account='true'` on every memory read/write, which the policy treats as “every row visible”. Pinning the role alone does not fix it. | `services/memory/app/db.py:39-57`, `org_context.py:11-23`, `000004_rls.up.sql:10,22`, `000009_create_directives.up.sql:104-118` |
| **P0-07** | Org deletion aborted on `idempotency_ledger.agent_id` (NOT NULL, NO ACTION) because the saga deletes agents first. | `000043_idempotency_ledger.up.sql:4-5`, `services/worker/app/tasks/org_deletion.py` |
| **P0-08** | Forget is a visibility tombstone: it nulls the embedding and sets `status='deleted'` but keeps `content` verbatim; the lifecycle outbox has no consumer. | `services/memory/app/lifecycle.py:_TOMBSTONE_SQL` |
| **P1-20** | ClickHouse purge covered 4 of 6 tenant tables; `usage_facts` and `evidence_events` survived. | `services/worker/app/tasks/org_deletion_stores.py` |
| **P1-24** | Object-store copies are not proven purged and there is no bucket lifecycle rule. | `10.data-lifecycle-and-deletion.md:107` |
| **D9** | Lifecycle, retention and legal holds are an open G0 decision. A legal-hold table, API and blocking exist; retention windows do not. | `28-g0-review-record-2026-11-06.md` D9 |

## 3. Implemented in this slice (branch `feat/w3-tenancy-erasure`)

- **P0-08** — forget overwrites `content` with a placeholder, replaces `content_hash` with a random value, zeroes
  `content_tokens`/`metadata`/PII flags, clears the lifecycle pointers, and deletes the label, feedback, relationship
  and conflict-escalation rows in the same transaction. The `forgotten` outbox event is the receipt. Proven by
  `test_forget_erases_content_and_child_labels` (sentinel absent, child rows 0, receipt present).
- **P0-07** — migration `000059_idempotency_ledger_agent_cascade` makes `agent_id` cascade with its agent.
  `test_org_postgres_purge_clears_idempotency_ledger` runs the real purge stage and asserts zero rows; it fails with
  `IntegrityError` when the migration is reverted.
- **P1-20** — `usage_facts` and `evidence_events` added to the ClickHouse purge and count queries.

**Reverted, deliberately:** the first P0-06 attempt (pinning `ibex_app` in memory, dropping the bypass) broke two
invariants and is not shipped half-built:

1. `directive_versions` is **append-only for `ibex_app`** — the migration test enforces it. The deletion saga cannot
   delete it as `ibex_app`; the purge needs an admin role.
2. The isolation suite is order-sensitive and started failing in a combined run; the fixtures seed with the bypass.

## 4. P0-06 design (not implemented)

**Role model.**

| Role | Attributes | Use |
|---|---|---|
| `ibex_app` | NOSUPERUSER, NOBYPASSRLS, NOLOGIN | Every tenant-facing transaction pins it (`SET LOCAL ROLE ibex_app`). Append-only tables stay append-only. |
| `ibex_service` | BYPASSRLS, NOLOGIN | Cross-tenant admin only: the org-deletion purge, the outbox relay. Never granted to `ibex_app`. |
| login role (deployment) | member of both | Connects; each transaction pins the role it needs. |

**Policy change.** Gate the bypass on the role, not the GUC alone:

```sql
row_org_id = current_setting('app.current_org_id', true)::uuid
OR (current_setting('app.is_service_account', true) = 'true' AND current_user = 'ibex_service')
```

Apply to `rls_org_visible` and the 13 inline policies. Remove `app.is_service_account` from every tenant path.

**Per-service pinning.** memory (`session_with_org`, `set_service_org`), worker (`ibex_idempotency.sessions`,
`session_as_service_org`), auth (`internal/repository/*.go`), proxy and the shared Go stores (`packages/session`,
`packages/directive`, `packages/modelpolicy`, `packages/ratelimit`, `packages/billing`). API and `mcp-operator`
already pin `ibex_app`.

**Auth exception.** `FindActiveByPrefix` is cross-tenant by design. Move it to a `SECURITY DEFINER` function that
accepts an exact prefix only, or to a login granted `ibex_service`. Do not widen a tenant role.

**Org deletion.** Run `_stage_postgres` as `ibex_service`: it bypasses RLS, filters by org explicitly, and needs
`DELETE` on the purge set (`session_events`, `legal_holds`, `directive_versions`, …), which `ibex_app` must not have.

**Proof.** Per-path cross-tenant negatives through the real session factories, with `app.is_service_account` never set:
memory get/search (vector + FTS), directive read, session read, operator routes, proxy chat; plus the forget negative
and the deletion negative.

## 5. D9 — owner decisions

Recommended: **narrowed soft delete + window + receipted purge.**

1. Retention window per data class (default 30 days) with an injectable clock, so CI proves both `window=0` (purge
   happens) and `window=30` (suppression only). *Note: the forget change above erases immediately; adopting a window
   moves the physical erase to the reaper.*
2. A legal hold blocks **physical purge only** (today's behaviour). The guide must say the data is suppressed but not
   erased.
3. “Erased” means content overwritten and child rows gone; the row remains for referential integrity.
4. Org deletion meeting an active hold stays `hold_blocked` until the hold is cleared.

## 6. Evidence boundary

The profile declares `IBEX_ORG_DELETION_DEPLOYED_STORES=postgres,redis`. In-profile evidence: Postgres zero-row
counts, Redis key absence, receipts and the finalize gate, `hold_blocked`, forget erasure, cross-tenant negatives.
ClickHouse and object-store purge must be proven in CI against ephemeral services and stay `provisional` — they are not
1.0 claims. Do not compress either into “org deletion erases all tenant data”; `ibex_billing` is retained by design.

## 7. Task order

1. Migration: role-gated policies + grants (tenant vs admin), no data movement.
2. Pinning: memory → worker → proxy/shared stores → auth, one service per change, each with its cross-tenant test.
3. Org deletion as `ibex_service`, with seeded ledger/budget/evidence and zero-row assertions.
4. CI: ephemeral ClickHouse/MinIO purge tests; keep them provisional.
5. Ledger rows: one for Postgres+Redis in-profile, one provisional for the projections.
6. D9 decision record before any retention-window claim.
