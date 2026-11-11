# Idempotency shape lapse — 2026-11-11

**Title:** The `idempotency-operation.v1` contract-shape acceptance lapsed on 2026-11-10 with no renewal recorded.
**Base:** `main` at `711f3655` (2026-11-11).
**Status:** Record of an **expired claim**. It renews nothing, downgrades nothing by itself, and names no reviewer. It
records that the acceptance window closed and that the decision the ledger requires is still outstanding.

## 1. What lapsed

`idempotency-operation.v1` is one of the five G0 contract shapes accepted by Rick1330 (acting owner across all roles; no
independent reviewer named) on **2026-10-10** (`21-g0-owner-decision-record.md:3,5`). Its review/expiry was set to
**2026-11-10** at that acceptance and has been carried at that date since.

It is the only one of the five that the **2026-11-06** G0 review did not re-verify, and that review said so plainly:

> There was therefore nothing to re-verify at the shape level, and its acceptance lapses on **2026-11-10** unless a
> future wave re-verifies it.
> — [`28-g0-review-record-2026-11-06.md`](28-g0-review-record-2026-11-06.md):78-80

The **2026-11-09** ledger review re-ran the evidence a renewal would need but did not renew it, because re-dating a
contract shape is a G0 acceptance act, not a test result. It required the decision itself to be recorded "on or before
2026-11-10" (`32-ledger-review-2026-11-09.md`:43-56).

**No renewal and no downgrade is recorded on or before 2026-11-10 in this repository.** As of 2026-11-11 the
contract-shape acceptance has therefore lapsed. Nothing else about it changed: the shape text was not rewritten, no
runtime row moved, and no gap closed.

## 2. Effect

The ledger's own rule applies (`00-status-and-evidence.md` §Rules): *"When a claim expires, downgrade it to `unknown`
or `provisional` until reverified."* The **contract-shape** acceptance is now `unknown` — expired, not renewed — until
the owner records one of the decisions in §3. These are the statements the controlled documents now carry:

| Document | Statement after this change |
|---|---|
| `00-status-and-evidence.md` (status line) | shape expired 2026-11-10, pending owner renewal or downgrade |
| `03-contract-registry.md` (status line, completion matrix, G1–G7 note, owner roles) | same |
| `18-gap-register.md` (GAP-001 row and closing note) | same |
| `21-g0-owner-decision-record.md` (next review, §4) | same |
| `site/content/docs/02.architecture/05.status-and-evidence.md` | same |
| `site/app/data/ledger.ts` (G0 gate evidence) | same |

**What did not lapse.** The nine `provisional` runtime rows were re-verified on 2026-11-09 at `df15390d` by running the
suites their evidence cells name, and carry 2027-02-06 (`32-ledger-review-2026-11-09.md`). Runtime evidence and
contract-shape acceptance are separate claims; the expiry of one does not re-open the other. In particular, the
`idempotency-operation.v1` proxy mutation and memory unification **runtime** slices keep their recorded
`provisional-with-evidence` / `provisional` status and their 2027-02-06 review.

## 3. The decision the owner still has to record

Only Rick1330, as acting owner across all G0 roles, can take it. No independent reviewer is named and this record does
not invent one. Both options must be recorded in `21-g0-owner-decision-record.md` and carried into
`00-status-and-evidence.md`, `03-contract-registry.md`, `18-gap-register.md`, and the two site sources in one change.

- **A — Renew the shape to 2027-02-06.** The evidence packet is `32-ledger-review-2026-11-09.md` §4: shared JCS
  fingerprint vectors, 12 conformance cases with PostgreSQL required, 6 real-PostgreSQL Go ledger tests including
  cross-org RLS isolation, the memory (852) and worker (459) unit suites, and the one additive term recorded since
  acceptance — an erased create key now replays as `409 IDEMPOTENCY_KEY_ERASED` (PR #1152). A renewal must state that
  it covers contract shape and safety semantics only, not runtime coverage.
- **B — Downgrade the shape.** Record it as `provisional`/`unknown` until re-verified, and state which evidence or
  contract change would restore it.

**Recommendation:** A, because the packet was assembled for exactly this act and the additive erased-key term is
already exercised by tests. B is the honest choice only if the owner judges the additive term, or the still-missing
shared JCS conformance and reconcile worker, too large to accept at shape level. Either decision is the owner's; this
record takes neither.

## 4. What this record does not verify

- It does not re-run the evidence suites. It cites `32-ledger-review-2026-11-09.md` for the run they record.
- It cannot establish that no decision was taken outside the repository. It establishes what the repository records,
  which is the only evidence available to it.
- It changes no runtime status, closes no gap, and promotes no row.
