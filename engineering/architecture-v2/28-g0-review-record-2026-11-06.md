# G0 Review Record — 2026-11-06

**Status:** Review performed. **One decision resolved** (D5, by ADR-0097); **D1, D4 and D6 reaffirmed open**; the four ledger rows for
`accepted` contract shapes re-verified with new evidence and re-dated; every `provisional` runtime row keeps its
2026-11-10 expiry and is assigned to the wave that re-verifies it. **No status is promoted, no gap is closed, and no
runtime work is authorised.**

**Reviewer:** Elshaday Mengesha / Rick1330, acting across all roles under the owner's written delegation for this
window. **No independent reviewer is named**, so D1 is reaffirmed open rather than assumed satisfied.

**Base:** `main` at `b400070f`, plus the decision under review,
[ADR-0097](../adr/0097-v1-supported-profile.md).

**Relationship to the packet:** this is the review event that
[`26-g0-review-packet.md`](26-g0-review-packet.md) scheduled for 2026-11-10. It does not replace that packet, and it
accepts nothing the packet itself does not already describe.

## 1. Why the review happened now

Before this review the ledger said review/expiry was 2026-11-10, **or earlier on a material profile or authority change**
(`00-status-and-evidence.md:3`). ADR-0097 selects a deployment profile for the first time in the repository's history,
which is precisely that trigger. Reviewing on 2026-11-06 rather than waiting four days is the rule being applied, not a
convenience.

Two further reasons:

- The profile decision could not be made honestly without testing the transport and deployability claims it depends on,
  and those tests produced a new blocker (P0-22, §6).
- The readiness audit's W1 exit gate is "signed profile + refreshed ledger". A decision record alone does not refresh
  the ledger; a review record does.

## 2. Decision outcomes

| ID | Decision | Outcome | Record |
|---|---|---|---|
| D1 | Named independent reviewer | **OPEN — reaffirmed.** The owner still acts across all roles. Nothing in this review substitutes for an independent reviewer, and every "independent review" precondition (GAP-001/002/004/006/007/011) remains unsatisfiable. | §7 |
| D2 | Round 5 contract-set mismatch | **OPEN.** Not in this wave's scope; owned by the contracts wave (W5) with D3. | — |
| D3 | Missing packet section and fields | **OPEN.** Same owner and wave as D2. | — |
| D4 | `required_evidence=false` relay gate | **OPEN — reaffirmed.** No PostgreSQL `required_evidence` column or setting exists. ADR-0097 keeps the relay optional and default-off and does **not** create the gate, so no wording may describe the relay as evidence-gated. | ADR-0097 §2, §4 |
| D5 | Supported profile | **RESOLVED.** `v1-single-node`: single-node self-hosted Docker Compose. The decision, its component set, transport contract, dependency matrix, exclusions and acceptance evidence are in ADR-0097. | ADR-0097 |
| D6 | Policy/principal trust | **OPEN — narrowed in consequence, not resolved.** `PrincipalContext` is still unsigned. ADR-0097 confines the plaintext context hop to a co-located loopback namespace, so the unsigned principal never crosses a network interface *in this profile* — which is why the profile can be selected without signing. Any non-loopback deployment, and any per-user authentication claim, remains unsupported. | ADR-0097 §4 |
| D7 | Budget scope | **OPEN.** Bounded-overshoot semantics are unchanged; no ratification is implied by this review. | — |
| D8 | Provider subset | **OPEN.** If unresolved at release time it is recorded as a 1.0 limitation, not an acceptance. | — |
| D9 | Lifecycle, retention, holds | **OPEN.** Needed by W3 (erasure) before a deletion-completeness claim can be made. | — |
| D10 | Durable conversation source | **OPEN.** The profile keeps the trace inspector metadata-only (ADR-0082), so this stays out of 1.0 rather than being decided by omission. | ADR-0097 §2 |
| D11 | Response-bound acknowledgement | **OPEN.** ADR-0097 §10 **excludes** response-bound acknowledgement from 1.0; the post-response boundary stands and must be stated wherever evidence is described. | ADR-0097 §2, §4 |
| D12 | MCP write disposition | **OPEN.** MCP writes are out of 1.0 scope; MCP memory is optional and default-off, MCP operator is unpublishable today. | ADR-0097 §2 |
| D13 | Recovery objectives | **OPEN.** Owned by W4; ADR-0097 requires a rehearsal but sets no number. | ADR-0097 §9, §11 |
| D14 | Provider invoice source | **OPEN.** Estimate-grade cost remains estimate-grade. | — |

**What "D5 resolved" means, precisely.** It means a profile is named, its exclusions are written down, and every later
gate has an environment to score against. It does **not** mean the profile runs: context, Console, edge termination, the
TEI pin and the migration publish job do not exist yet, and AuthService has no TLS. P0-17 therefore closes at the
decision level while P0-01, P0-02 and the new P0-22 stay open.

## 3. Contract-shape re-verification

Five contract shapes are `accepted` (2026-10-10). Four of them carry an `accepted` ledger row: `principal-context.v1`,
`evidence-envelope.v1`, `evidence-relay-sink.v1` and `run-envelope.v1`. The fifth, `idempotency-operation.v1`, is recorded
in the contract registry and its ledger entries are runtime slices that are `provisional*`; it therefore has no accepted
row to re-verify and no date moved. The four rows below are `accepted` as contract text and safety semantics only. The ledger's rule is explicit that
re-dating them without new evidence would be a promotion in disguise (`26-g0-review-packet.md` §7.1), so each was
re-verified at head before its review date moved.

| Shape | What was checked | Command | Result |
|---|---|---|---|
| `principal-context.v1` | Contract text unchanged since 2026-10-10 (`04-principal-policy-and-run.md` content was only relocated by the site move in `72f706b3`); the proto contract and the proxy principal/binding/policy-snapshot middleware still pass at head | `go test -count=1 ./packages/proto/...` and `go test -count=1 -v ./services/proxy/internal/http/ -run 'Principal\|PolicySnapshot\|AgentBinding'` | exit 0; 39 and 49 passing test results (including subtests) |
| `evidence-envelope.v1` | No edit to the `evidence-envelope.v1` section since 2026-10-10; the file gained two **additive** operator read-model sections (`operator.evidence.summary.v1`, `operator.evidence.deletions.v1`), each a separate contract. Producer sanitizer/fence and outbox tests pass at head | `go test -count=1 ./packages/evidenceoutbox/... ./packages/session/... ./services/proxy/internal/http/session/...` | exit 0 |
| `evidence-relay-sink.v1` | Contract text unchanged; relay bootstrap, config and fence suites pass at head. The ClickHouse adapter remains a non-production pilot | `go test -count=1 ./services/relay/...` | exit 0 |
| `run-envelope.v1` | Contract text unchanged; still design-only — no runtime type, persistence, replay, or approval consumption exists to test. Re-verified as contract text **with the same limitation**, which is why the row keeps that limitation verbatim | inspection of `04-principal-policy-and-run.md`; no code path exists | no runtime evidence claimed |

The combined run over the evidence, session, relay and idempotency packages executed **437 passing test results** (including subtests) and exited 0
(`go test -count=1 -v ./packages/evidenceoutbox/... ./packages/session/... ./packages/idempotency/... ./services/relay/... ./services/proxy/internal/http/session/...`).

**Outcome:** all four shapes are **reaffirmed** at `b400070f`, with their limitations unchanged and their review date
moved to 2027-02-06.

**What this review did not renew:** `idempotency-operation.v1`. The shape is `accepted` in the registry, but it has no
`accepted` ledger row — its ledger entries are runtime slices, and those are `provisional`. There was therefore nothing
to re-verify at the shape level, and its acceptance lapses on **2026-11-10** unless a future wave re-verifies it. That
asymmetry is deliberate and is stated in the registry, the decision record and the ledger header, so that no reader
treats all five shapes as current until 2027-02-06. The status value does not change: they remain `accepted` for contract text and safety semantics
only, and no runtime seam is promoted.

## 4. What was not re-verified, and why

Every `provisional` and `provisional-with-evidence` runtime row keeps its 2026-11-10 expiry in this review. Re-dating
them now would claim evidence in an environment that does not exist yet: the profile was selected today and cannot be
started. Each row is assigned to the wave that will produce profile evidence for it.

| Runtime row group | Re-verified by | What the wave must run |
|---|---|---|
| GAP-001 idempotency slices | W3 / W5 | PostgreSQL ledger round-trip and the shared conformance vectors under the profile, with non-superuser roles |
| GAP-002 policy snapshot | W5 | Issuance → verification round-trip with rotation, in the profile |
| GAP-004 proxy SLO | W6 | A measurement with runner profile, percentile set, error policy and artifact digests |
| GAP-006 budget slice | W3 | Claim/finalize/replay/release against the profile database with RLS enforced |
| GAP-007 lifecycle and forget | W3 | A forget that erases content, plus the org-deletion path reaching `succeeded` with zero rows |
| GAP-011 relay daemon and session evidence | W4 / W5 | Fence-checker suite and a delivered batch in the profile, with the sink it actually ships |
| Console read paths | W9 | The clean-browser journey, with a negative two-tenant case |
| Context assembly | W2 / W3 | The co-located hop with caller authentication and a cross-tenant negative |

## 5. New blocker found by the profile review

**P0-22 — the chat path cannot authenticate outside `development`.** Diagnosed per hop, because a single verdict would
be wrong: the Go proxy dials TLS for every `IBEX_ENV` except `development`, while AuthService registers no server
transport credentials, so **proxy → auth always fails outside `development`** — and every chat request needs that hop.
The Python API dials `grpc.aio.insecure_channel` behind `assert_trusted_insecure_auth_target`, so **API → auth works**
over a Compose short name, but with no transport security. The Console BFF refuses a session cookie over a non-HTTPS API
origin, and there is no TLS terminator in the Compose path (the Helm ingress `tls:` block is scaffolding that needs an
operator secret and belongs to the excluded Kubernetes profile). The stack can be started today only with
`IBEX_ENV=development`, which is not a production posture. Recorded in
[`27-v1-readiness-audit.md`](27-v1-readiness-audit.md) §3.1 with ADR-0097 §4 as the decision that resolves the transport
question and W2 as the implementation.

## 6. Claim boundary after this review

- The four `accepted` contract shapes remain `accepted` for **contract text and safety semantics only**, re-verified at
  `b400070f` on 2026-11-06, with no separate reviewer.
- No `provisional` runtime row changes value. Their expiry is unchanged.
- `GAP-001`–`GAP-012` statuses are unchanged. **No gap is closed.**
- The profile decision is a decision. It is not evidence that anything runs, and no public page may describe
  `v1-single-node` as available, supported, or started until W2's acceptance evidence exists.
- D1 stays open, so the `provisional` floor remains in force for every gap with an independent-review precondition.

## 7. Why D1 is not resolved here

The review has an owner and a date and no second person. Recording it as an independent review would be false, and
naming an agent as the independent reviewer would be a role-playing exercise, not independence: the same operator
configures the agents, writes the prompts, and can read the working tree. The honest options remain the two in the
packet: record a human reviewer, or explicitly reaffirm that none is assigned. This record takes the second option and
keeps every consequence of it.

## 8. Next review

The next review is due **2027-02-06**, or earlier on any of:

1. the first successful start of `v1-single-node` (which is when runtime rows can actually be re-verified);
2. any change to an accepted contract's text or safety semantics;
3. any change to the selected profile, its component set, or its transport contract;
4. resolution of D1, D4 or D6;
5. any authority change — a second person joining as reviewer or maintainer.

Trigger 1 will fire long before 2027-02-06 in any successful 1.0 path, and the review it triggers must re-verify the
runtime rows rather than re-date them.
