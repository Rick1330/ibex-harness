# Ledger review — 2026-11-09

**Title:** Re-verification of the nine `provisional` runtime rows before their 2026-11-10 expiry.
**Base:** `main` at `df15390d` (2026-11-09), `v1-single-node` selected by [ADR-0097](../adr/0097-v1-supported-profile.md).
**Status:** Review record. It re-dates runtime rows whose evidence was re-run and leaves every status and limitation in place. It does **not** renew the `idempotency-operation.v1` contract-shape acceptance; that is an owner act (§4).

## 1. Why this review exists

The 2026-11-06 G0 review re-verified the four `accepted` contract shapes and re-dated only those rows. Nine
`provisional` runtime rows kept a 2026-11-10 review date, with the rule that "they are re-verified by the wave that
owns each one, because re-dating them before the profile runs would be a promotion in disguise". The profile has since
started (`29-v1-single-node-start-record-2026-11-07.md`), so the rows were due. Each was re-checked by running the
suite its own evidence cell names, at `df15390d`. No status changes.

## 2. What was run

All commands were run on the review host against PostgreSQL 16 + pgvector `0.8.6-pg16` and Redis 7.4.2, with the
schema migrated to `000062`. PostgreSQL and Redis were confirmed reachable immediately before the DB-backed runs.

| Row | Re-verified with | Result |
|---|---|---|
| `idempotency-operation.v1` proxy mutation slice | `go test -tags=integration -run TestIntegration_PostgresLedger ./packages/idempotency/` | 6 real-PostgreSQL tests pass: claim/finalize/replay, hash conflict, reclaim fence, release/stale release, invalid claim, **RLS cross-org isolation** |
| `idempotency-operation.v1` memory unification slice (#1006) | shared package `go test`; memory unit; worker unit; `infra/tests/idempotency-conformance` with `IBEX_IDEMPOTENCY_CONFORMANCE_REQUIRED=1` | package 33 pass; memory 852 pass at 98.54% (gate 95%); worker 459 pass / 6 skipped; conformance **12 pass, 0 skip** (previously 2 pass / 10 skip) |
| GAP-004 proxy SLO ratification + benchmark gate | `python3 benchmarks/scripts/test_pipeline.py` | `Ran 40 tests`, `OK (skipped=1)` — unchanged from the recorded run |
| GAP-006 budget reservation slice (#1000) | `go test -tags=integration -run 'TestBudgetReservations' ./infra/migrations/postgres/`; `go test -race ./packages/budgetledger/...`; worker integration `-k budget` | 4 migration tests pass (schema+RLS, constraints, agent cascade, down); race suite pass; 14 worker budget/idempotency tests pass |
| Evidence relay contract hardening | `go test -tags=integration -race -p 1 ./packages/evidenceoutbox/...` | 66 tests pass under `-race`, including the PostgreSQL store and RLS suites |
| GAP-011 evidence relay daemon (#1002) | `go test -tags=integration -run 'TestRelayFenceChecker' ./infra/migrations/postgres/`; `go test -tags=integration -race -p 1 ./services/relay/...` | 4 migration tests pass (definition/grants, fence outcomes, role isolation, down); relay bootstrap/config/fence suites pass under `-race`, including the real-PostgreSQL fence checker |
| Session evidence producer slice | `go test -tags=integration -p 1 ./services/proxy/internal/http/session/... ./packages/session/...` | session, session/evidence and the full `packages/session` suite pass |
| GAP-007 historical conflict candidates | memory unit + the full PostgreSQL memory integration suite | memory 852 pass; integration 114 pass (historical search, conflict-candidate load, supersession, forget, RLS pinning) |
| GAP-002 runtime policy snapshot slice (#997) | `go test -race ./packages/policysnapshot/...`; `go test ./services/auth/... ./services/proxy/...`; `buf lint` | policysnapshot race suite pass; 27 Go packages pass; `buf lint` exit 0 |

## 3. What this review did **not** verify

- **ClickHouse.** No ClickHouse instance is available on the review host; the relay sink remains a non-production pilot,
  exactly as the rows say.
- **Hosted/HA behaviour, a measured p99, and a browser journey.** None is in scope for a runtime row's local evidence.
- **A restore.** That is W4 of the release plan and is the largest remaining gap; it is not claimed here.

Every row keeps its limitation text unchanged, because none of those limitations was retired by this review.

## 4. The one row this review cannot renew

`idempotency-operation.v1` is one of the five **accepted contract shapes**, and it is the only one whose contract-shape
acceptance was not re-verified on 2026-11-06. It therefore still lapses on **2026-11-10**. Re-dating it is a G0
acceptance act, not a test result; this review instead prepares the evidence for it:

- the shared JCS fingerprint contract: 2 vectors, plus the shared-ledger contract cases, **12 pass with PostgreSQL
  required** (previously 10 skipped);
- the Go ledger: 6 real-PostgreSQL integration tests, including cross-org RLS isolation;
- the memory and worker slices: 852 + 459 unit tests, and the memory integration suite at 114;
- one contract addition since acceptance, from PR #1152: a create whose memory was forgotten now stores a content-free
  marker and answers **`409 IDEMPOTENCY_KEY_ERASED`** on replay instead of the erased body. That is additive to the
  accepted text (a terminal error, not a changed success shape) but it must be recorded before renewal.

**Recommendation:** the owner renews `idempotency-operation.v1` to 2027-02-06 with the four items above as the
evidence, or downgrades it — either decision has to be recorded on or before 2026-11-10.

## 5. Effect on the ledger

Nine rows: `Verified` gains `2026-11-09`, `Review` moves to `2027-02-06`, status and limitations unchanged. The
`idempotency-operation.v1` contract shape is **not** re-dated by this record.

Re-dating is not promotion: no row moves from `provisional` to `shipped-accepted`, and the claim rule's evidence
requirements are unchanged.
