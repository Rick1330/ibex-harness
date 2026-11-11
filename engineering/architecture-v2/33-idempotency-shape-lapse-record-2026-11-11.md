# Idempotency shape lapse and renewal — 2026-11-11

**Title:** The `idempotency-operation.v1` contract-shape acceptance lapsed on 2026-11-10 and the owner renewed it on
2026-11-11 to 2027-02-06.
**Base:** `main` at `711f3655` (2026-11-11).
**Status:** Record of a **lapse and the renewal that followed it**. The lapse is kept because it happened: the claim was
expired for one day, and any reader checking the tree on 2026-11-10 would have found no live acceptance to cite. The
renewal was taken by the owner on 2026-11-11. No reviewer is named or invented.

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

**No renewal and no downgrade was recorded on or before 2026-11-10.** The acceptance therefore lapsed at that date. Under
the ledger's own rule (`00-status-and-evidence.md` §Rules) — *"When a claim expires, downgrade it to `unknown` or
`provisional` until reverified"* — the shape was `unknown` for the gap between expiry and renewal. Nothing else about it
changed during the gap: the shape text was not rewritten, no runtime row moved, and no gap closed.

## 2. The renewal

On **2026-11-11** the owner, **Elshaday Mengesha / Rick1330**, acting across all G0 roles, renewed the
`idempotency-operation.v1` contract-shape acceptance to **2027-02-06**. The basis the owner gave, recorded here verbatim
in substance:

- the evidence packet in [`32-ledger-review-2026-11-09.md`](32-ledger-review-2026-11-09.md) §4 — shared JCS fingerprint
  vectors, 12 conformance cases with PostgreSQL required, 6 real-PostgreSQL Go ledger tests including cross-org RLS
  isolation, the memory (852) and worker (459) unit suites; **plus**
- the additive term introduced by PR #1152: an erased create key now replays as `409 IDEMPOTENCY_KEY_ERASED`, a terminal
  error rather than a changed success shape.

The renewal carries the same scope as the 2026-10-10 acceptance: **contract shape and safety semantics only**. It
promotes no runtime seam, closes no gap, and authorizes no hosted/HA claim. The decision is recorded in
`21-g0-owner-decision-record.md` (`**Renewal:**` and `**Next review:**`), and carried into
`00-status-and-evidence.md`, `03-contract-registry.md`, `18-gap-register.md`, `31-v1-release-plan-2026-11-09.md`, and the
two site sources.

These are the statements the controlled documents now carry:

| Document | Statement after this change | Review/expiry |
|---|---|---|
| `00-status-and-evidence.md` (status line, owner log) | re-accepted 2026-11-11 on the §4 packet plus the 409 term | 2027-02-06 |
| `03-contract-registry.md` (status line, completion matrix, G1–G7 note, owner roles) | renewed 2026-11-11; row back to `accepted` | 2027-02-06 |
| `18-gap-register.md` (GAP-001 row and closing note) | lapsed 2026-11-10, renewed 2026-11-11 | 2027-02-06 |
| `21-g0-owner-decision-record.md` (`**Renewal:**`, next review, §4) | the decision act itself | 2027-02-06 |
| `31-v1-release-plan-2026-11-09.md` (P0-16, 0.1, D-E) | closed by the owner's renewal, with the lapse kept | 2027-02-06 |
| `site/content/docs/02.architecture/05.status-and-evidence.md` | same state as the canonical ledger | 2027-02-06 |
| `site/app/data/ledger.ts` (G0 gate summary and evidence) | same state as the canonical ledger | 2027-02-06 |

**What did not change at either date.** The nine `provisional` runtime rows were re-verified on 2026-11-09 at `df15390d`
by running the suites their evidence cells name, and carry 2027-02-06 (`32-ledger-review-2026-11-09.md`). Runtime
evidence and contract-shape acceptance are separate claims; neither the lapse nor the renewal re-opened the other. In
particular, the `idempotency-operation.v1` proxy mutation and memory unification **runtime** slices keep their recorded
`provisional-with-evidence` / `provisional` status and their 2027-02-06 review.

## 3. Why the lapse stays on the record

A claim that expired and was then renewed is a stronger record than one that appears never to have lapsed:

- It dates the gap. Between 2026-11-10 and 2026-11-11 the correct reading of this shape was `unknown`, and a sign-off
  citing it in that window would have rested on an expired claim.
- It keeps the owner act visible. The renewal is a dated decision with a stated basis, not an untracked edit to a date.
- It leaves the next review honest. The shape's review/expiry is 2027-02-06 because the owner set it on 2026-11-11, not
  because a review date was quietly overwritten.

## 4. What this record does not verify

- It does not re-run the evidence suites. It cites `32-ledger-review-2026-11-09.md` for the run they record; the renewal
  was taken on that packet, and nothing here claims the suites were re-executed on 2026-11-11.
- It cannot establish that no other decision was taken outside the repository. It records the owner's stated decision
  and what the repository now says.
- It names no independent reviewer. The acceptance remains an acting-owner decision across all G0 roles, so D1 stays
  open exactly as `21-g0-owner-decision-record.md` and `28-g0-review-record-2026-11-06.md` §7 record.
- It changes no runtime status, closes no gap, and promotes no row.
