---
title: "ADR-0094: Bounded lineage traversal and unresolved-conflict suppression are read-path properties"
description: "Architecture decision record 0094: a depth-capped, tenant-scoped recursive CTE walks memory_relationships in both directions, and unresolved conflict escalations suppress the lower-ranked side of a contradiction on search, hot cache, and context assembly."
adrId: "0094"
status: "Proposed"
date: "2026-11-03"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Proposed" date="2026-11-03" id="0094"}
::

# ADR-0094: Bounded lineage traversal and unresolved-conflict suppression are read-path properties

- **Status:** Proposed
- **Date:** 2026-11-03
- **Author:** Elshaday Mengesha (@Rick1330)
- **Related:** [ADR-0049](0049-memory-relationship-graph.md), [ADR-0057](0057-conflict-escalation.md), [ADR-0068](0068-composite-relevance-gate.md), [ADR-0069](0069-context-packing-knapsack.md), [ADR-0092](0092-hybrid-retrieval-rrf-admission.md).
- **Implementation:** `services/memory/app/read/lineage.py`, `services/memory/app/read/conflicts.py`, `services/memory/app/routers/memories.py`, `services/context/app/conflict.py`, `services/mcp-memory/app/tools.py`; milestones 5.B.1–5.B.3.

## Context

Three facts about the memory read path made this decision necessary.

1. `ibex_core.memory_relationships` records why a memory is no longer current, and
   `ibex_core.resolve_supersession_tip` resolves one supersession chain head. Nothing walked the graph further: the
   operator detail view shows one hop, and no service exposed a chain. An agent could see that a memory was superseded
   but not the memory that replaced it.
2. The phase 5 milestone sketch says an unresolved contradiction is "two candidates with a `contradicts` edge and no
   resolution". In this codebase `insert_relationship` has **no production caller**, so no `contradicts` edge is ever
   written. Unresolved conflicts live in `ibex_core.memory_conflict_escalations` with `status = 'pending'`, written by
   the conflict stage when it escalates instead of auto-superseding (ADR-0057).
3. Context assembly merges a hot-cache page and a cold-search page. Each page is filtered on its own, so two memories
   that contradict each other could both reach the formatter — the exact failure the milestone calls out: the model
   receives two claims and no way to choose.

The question this record settles is where traversal limits and conflict suppression belong, and what the authority for
"unresolved conflict" is.

## Decision

1. **Traversal lives in SQL, not in application loops.** `MemoryLineageRepository` issues one recursive CTE over
   `memory_relationships`. The depth cap (`≤ 5`, default `3`) and the cycle break are properties of the query, so no
   request can ask for an unbounded walk and no application bug can loop.
2. **`org_id` is applied at every recursion level**, not only at the base case: the edge join, the next-node join, and
   the far-end join each carry it. The composite foreign keys already guarantee it; the explicit predicate is what makes
   the guarantee local to the query that depends on it.
3. **Both directions are walked.** "What replaced this" and "what did this replace" are the same question asked from
   opposite ends, and a caller that has to issue two requests will get them in two different states. Each edge carries
   `from_memory_id`, so a consumer can rebuild the chain without inferring direction from `depth`.
4. **The result is bounded twice.** Depth in the query, and `MAX_LINEAGE_EDGES` (100) on the projection, with a
   `truncated` flag when a further edge exists. A dense node cannot turn one request into an unbounded response.
5. **"Not visible" is one answer.** A memory outside the token organization is `404`. An agent-scoped token's agent is
   applied to the root *and to every joined node*, so an edge cannot hand back another agent's memory id, status, or
   relationship type — the same boundary search and hot cache already enforce. Distinguishing "wrong tenant" from
   "does not exist" would be an existence leak, exactly as in the rest of the read path.
6. **The chain head is a property of the memory, not of the request.** `supersession_tip` is resolved with the helper's
   own maximum depth, not with the caller's `max_depth`; otherwise `max_depth=1` would report the immediate successor
   as "current" for a three-link chain, and a client that trusts the field would re-serve a superseded memory. The
   resolution is re-scoped to the caller's tenant and agent, falling back to the memory itself, so the field cannot
   become a cross-agent id leak.
7. **Pending conflict escalations are the authority for "unresolved".** Not `contradicts` edges: suppressing on a
   relationship type nothing writes would suppress nothing and look correct in tests. `contradicts` edges remain a
   first-class lineage edge when one exists (the operator may write them), but escalation status decides suppression.
8. **Each hydrated row carries the set of pending escalation ids it belongs to.** The set is a correlated subquery on
   the hydration statement that already runs, so the common case (no conflicts in the page) costs no extra round trip.
   Returning a *set* rather than one group id is what makes the rule correct when a memory sits in two escalations.
   The ids are **org-scoped, not agent-scoped**: an escalation has no owner column, only its two memory endpoints. An
   agent-scoped page can therefore carry the opaque id of an escalation whose other side belongs to a peer agent. It
   never carries that memory's id or content, and the peer row is never in the page, so nothing is suppressed or
   revealed beyond an opaque UUID; the escalation exists inside the caller's own organization.
9. **Suppression is pairwise and greedy by rank.** The highest-ranked hit is kept; any later hit whose set intersects
   the kept set is dropped. The survivor set is guaranteed to contain no conflicting pair, which is the property the
   packer needs.
10. **Suppression runs before the page is cut**, so a conflicting pair costs one slot rather than shortening the page.
    In the hybrid path the dropped slot is refilled from the remaining fused candidates; in the sparse fallback the
    full-text supplement is sized from the post-suppression page, so an eligible GIN match fills it. The reranked path
    has no unhydrated remainder inside its window (the window is already the widest the settings allow), so a reranked
    page may legitimately come back one shorter. Hot cache applies the same collapse to its ZSET order.
11. **The Tier-1 PII re-check runs before the collapse.** A blocked higher-ranked side would otherwise suppress its
    counterpart and then vanish itself, turning two recoverable hits into a short or empty page — the same hazard the
    rerank stage already avoids by excluding blocked rows from the ranking input. This holds on the hot-cache page too.
12. **Context assembly reruns the rule across hot + cold.** The memory service cannot see across two pages, so the
    merge re-applies it with the same sets, ordered by the packer's interim score (the only comparable ordering across
    a write-time ZSET score and a query similarity). Both sides never reach the formatter.
13. **"A superseded memory never outranks its successor" is structural, not a scoring rule.** Both hydration statements
    fence `status = 'active'`, so a superseded memory is not a candidate. This ADR records the property and the
    regression test that proves it rather than inventing a scoring adjustment for something already true.
14. **The traversal carries its own statement timeout.** The edge cap bounds the response, not the recursive work: path
    enumeration grows with fan-out, and a dense graph could hold a pooled connection far longer than a read may. A local
    `statement_timeout` of `500ms` turns that into a fast `503` instead of a request that never returns.

## Alternatives considered

- **Walk the graph in Python, fetching neighbours per hop.** Rejected: N+1 round trips on a latency-sensitive read path,
  and the depth cap would then live in application code where a refactor can lose it.
- **Apache AGE or a dedicated graph database.** Rejected for now, matching the milestone's own ranking: the graph is
  shallow, and staying in Postgres keeps tenant isolation in one place with the RLS policy that already covers the table.
  Revisit only if traversal shape or volume outgrows a bounded recursive CTE.
- **`contradicts` edges as the suppression authority.** Rejected: nothing writes them, so the filter would be dead code
  with a passing test. It would also duplicate the escalation table, which is the durable record the conflict stage
  already owns.
- **A transitive-closure conflict group** (union-find over pending pairs). Rejected: pairwise against the kept set gives
  the same survivor set in the common case and a smaller, more predictable one when one memory conflicts with two
  others — the model gets the winner, not one member of an arbitrary equivalence class.
- **Returning a short page instead of refilling.** Rejected: the ADR-0068 refill already exists for rows dropped below a
  floor or by the PII guard, and a conflict drop is the same kind of drop.
- **Collapsing only in the packer, from a memory-service call.** Rejected: an extra network call inside the assembly
  deadline for data the search response can carry for free.
- **One pending-escalation id per row instead of the set.** Rejected: wrong when a memory is escalated against two
  candidates, and wrong in a way that is invisible until an agent sees both sides.

## Consequences

- Two additive partial indexes are required for the row-local lookup:
  `idx_memory_conflict_escalations_org_new_pending` and `idx_memory_conflict_escalations_org_candidate_pending`
  (`(org_id, <side>) WHERE status = 'pending'`, migrations `000057`/`000058`). The existing
  `(org_id, created_at DESC)` index serves the worker poll, not this lookup.
- `POST /v1/memories/search` and `GET /v1/memories/hot` now include `conflict_groups` per hit. It is additive and
  defaults to an empty list, so a consumer that ignores it sees no change; the context client treats the field as
  optional for the same reason.
- An agent-scoped token traverses only its own agent's nodes; an org-scoped token sees the whole organization's graph.
  The same root therefore yields different edge sets for the two callers, which is the intended boundary, not an
  inconsistency.
- Suppression can shorten a fallback page when there is no further candidate to refill from — a genuine short page,
  never two sides of one contradiction. In the reranked path a short page is expected: there is nothing left inside the
  window to refill from.
- A conflict-free page pays two index probes per hydrated row and one set operation; a page with a conflict pays one
  dropped candidate and, when a refill is possible, one extra hydration batch. No new network hop.
- `ibex_memory_conflict_suppressed_total` counts hits dropped from the ranked candidate set that produced the page,
  before the page is sliced to `limit`; it is not a count of "results missing from the response".
- Context assembly now sorts merged hot + cold hits by the interim score before `max_memories` applies. That is the same
  canonical order the packer already imposed, but it means `max_memories` selects the highest-scoring hits rather than
  the first N in hot-then-cold arrival order.
- The lineage traversal is bounded by depth, by the edge cap, and by a `500ms` local statement timeout. A dense graph
  answers `503` instead of holding a pooled connection; the `error` label on `ibex_memory_lineage_queries_total` makes
  that visible.
- The 1M-row P99 latency signal in milestone 5.B.1 is **not** measured by this change. The integration suite asserts the
  traversal's correctness (depth cap, cycle, tenant and agent scope, truncation) and a smoke latency bound; producing
  the published 3-hop/5-hop P99 requires the benchmark environment and a `benchmarks/memory` runner. Until that number
  exists, no latency claim is made.

## References

- [ADR-0049](0049-memory-relationship-graph.md) — the relationship table, its org-scoped indexes, and
  `resolve_supersession_tip`.
- [ADR-0057](0057-conflict-escalation.md) — the escalation table and the conflict outcomes that write it.
- [ADR-0068](0068-composite-relevance-gate.md) — the composite ordering, relevance floor, and the refill rule.
- [ADR-0069](0069-context-packing-knapsack.md) — the packer that consumes the merged, conflict-free candidate list.
- PostgreSQL documentation, recursive queries and cycle detection
  (<https://www.postgresql.org/docs/16/queries-with.html>).
