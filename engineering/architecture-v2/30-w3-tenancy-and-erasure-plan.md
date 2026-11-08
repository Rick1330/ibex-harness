# W3 — Tenancy and Erasure: plan and current state

**Status:** planning record. Slice 1 is implemented on `feat/w3-tenancy-erasure`: erasure, the deletion cascade, the
six-table purge, and the **memory-service** P0-06 pin. The worker, auth, proxy and shared Go stores still connect as the
owner role; their pinning is the next slice.

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
  `content_tokens`/`metadata`/PII flags, clears the lifecycle pointers, deletes the label, feedback, relationship and
  conflict-escalation rows, and scrubs the finalized idempotent create response (matched on `data.id`, never on a
  substring) in the same transaction. The `forgotten` outbox event is the receipt. Proven by
  `test_forget_erases_content_and_child_labels` (sentinel absent from the row and the ledger, a near-duplicate
  create's row untouched, child rows 0, receipt present).
- **P0-07** — migration `000059_idempotency_ledger_agent_cascade` makes `agent_id` cascade with its agent.
  `test_org_postgres_purge_clears_idempotency_ledger` runs the real purge stage and asserts zero rows; it fails with
  `IntegrityError` when the migration is reverted.
- **P1-20** — `usage_facts` and `evidence_events` added to the ClickHouse purge and count queries.

**P0-06 (memory only) is in this slice:** memory transactions pin `ibex_app` and no longer set
`app.is_service_account`; the vector store pins through the same helper; an unfiltered `SELECT` test and a
cross-tenant forget test prove it. The worker, auth, proxy and the shared Go stores are **not** pinned yet. Two
invariants shaped the split:

1. `directive_versions` is **append-only for `ibex_app`** — the migration test enforces it. The deletion saga cannot
   delete it as `ibex_app`; the purge needs an admin role.
2. The isolation suite is order-sensitive and started failing in a combined run; the fixtures seed with the bypass.

## 4. P0-06 design (memory landed; the rest is the next slice)

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

## 5. D9 — decision (2026-11-08)

Options considered, ranked by fit for a single-node self-hosted profile:

| Rank | Model | Why not chosen / chosen |
|---|---|---|
| 1 | **Immediate erasure + documented backup boundary + hold blocks destruction** | **Chosen.** Satisfies storage limitation directly; no reaper whose window cannot be evidenced without a clock harness; the EDPB/ICO position is that erasure must reach backups *or put them beyond use with re-deletion after restore*, which is a recovery-wave obligation, not a reason to keep live content. |
| 2 | Soft delete + retention window + receipted purge | Honest for recoverability, but needs a reaper, an injectable clock, per-class windows, and a purge receipt per memory; none of it is required by the exit gate, and a window that is not enforced is a false claim. |
| 3 | Per-store policy | The profile runs Postgres + Redis only; ClickHouse and object storage are default-off, so the policy surface would exceed the environment. |

**Decisions:**

1. **Forget erases immediately.** Content is overwritten and child rows deleted in the same transaction as the
   tombstone; the row is retained with no content for referential integrity and as the deletion marker (EDPB/ICO
   practice: a non-identifiable marker plus a date).
2. **A legal hold blocks destruction.** Forget is refused with `LEGAL_HOLD_ACTIVE` (409) while a hold is active, not
   only the org purge: a hold is a legal obligation to preserve, which is a recognised ground to refuse erasure
   (GDPR Art. 17(3)). Clearing the hold re-enables forget.
3. **Backups are out of scope for this profile and stated as such.** The guide records that backup copies are not
   erased by forget and that a restore must re-apply the deletion markers before serving traffic (recovery wave).
4. **Org deletion meeting an active hold stays `hold_blocked`** until the hold is cleared.
5. **“Zero rows” means tenant content tables.** Receipts (`org_deletion_jobs`, `deletion_store_receipts`,
   `memory_lifecycle_outbox`), billing history (`ibex_billing.*`) and `failed_tasks` are retained by design and listed
   in the guide; the claim never compresses them into “all tenant data”.

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
