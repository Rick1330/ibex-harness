---
title: "ADR-0092: Hybrid retrieval fuses by RRF for admission and keeps composite scoring for presentation"
description: "Architecture decision record 0092: the memory read path runs dense and sparse channels in parallel, admits candidates by reciprocal rank fusion with k=60, and leaves ADR-0068 composite scoring as the only presentation order."
adrId: "0092"
status: "Proposed"
date: "2026-11-02"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Proposed" date="2026-11-02" id="0092"}
::

# ADR-0092: Hybrid retrieval fuses by RRF for admission and keeps composite scoring for presentation

- **Status:** Proposed
- **Date:** 2026-11-02
- **Author:** Elshaday Mengesha (@Rick1330)
- **Related:** [ADR-0068](0068-composite-relevance-gate.md), [ADR-0053](0053-vector-store-abstraction.md), [ADR-0060](0060-memory-service-tenant-isolation.md).
- **Implementation:** `services/memory/app/read/fusion.py`, `services/memory/app/read/ranking.py`, `services/memory/app/read/repository.py`; issue #1096, PR #1097.

## Context

`find_similar` has two retrieval channels: pgvector HNSW with cosine similarity, and Postgres full-text search with
`ts_rank_cd` over a GIN index. They were sequenced, not combined: vector ANN ran first and the full-text channel ran only
when the vector page came back short (`search_fallback_enabled and vector_count < limit`).

That gate has a structural blind spot. When vector fills the page — the ordinary case for a dense embedding — the
full-text channel never runs, so a memory that matches an exact token or identifier but sits just outside the ANN top-k
is unreachable even though `ts_rank_cd` would rank it first. The merge was also a plain union, so the two channels'
ranks never informed each other.

The two channels score on incomparable scales. Cosine similarity is bounded and dense; `ts_rank_cd` is unbounded and
depends on document length and term frequency. Any weighted sum of the two needs a normalisation that cannot be defended
from the data, and this repository already carries a fixed `0.5` relevance sentinel for full-text hits precisely because
the scales do not meet.

## Decision

1. **Both channels run for every searchable query**, independent of how full the vector page is. Each channel is capped
   at `limit`, so the union of candidate ids never exceeds `2 × limit`.
2. **Reciprocal rank fusion orders the union**: `score(d) = Σ 1/(k + rank(d))` over the channels that returned `d`.
   Ranks start at 1. `k` defaults to `60` — the constant in Cormack, Clarke and Büttcher (SIGIR 2009) and the
   `rank_constant` default in Elasticsearch's `rrf` retriever — and is configurable through
   `IBEX_MEMORY_SEARCH_RRF_K` in the range 1..1000. Ties break on memory id so identical inputs produce identical order.
3. **Fusion decides admission; composite scoring decides presentation.** Only the top `limit` fused candidates are
   hydrated, so hydration is bounded by the page size. ADR-0068 composite scoring then orders that window unchanged,
   including its weights, its relevance floor, and the full-text `0.5` relevance sentinel.
4. **A candidate keeps its own channel score** — cosine for a vector hit, clamped `ts_rank_cd` for a full-text hit — and
   a duplicate keeps the vector candidate. Fusion reorders ids; it does not invent scores.
5. **Rollout is a flag, not a default.** `IBEX_MEMORY_SEARCH_HYBRID_ENABLED` ships `false`; the previous path is intact
   and is what runs when the flag is off. Promoting it to the default is a separate, measured decision.

## Alternatives considered

- **Weighted score fusion with per-channel normalisation** (min-max or z-score over each page). Rejected: the
  normalisation depends on the page, so the same memory can be admitted or rejected depending on which other memories
  happened to be retrieved. RRF needs only ranks and is stable under that.
- **RRF as the final order**, replacing composite scoring. Rejected for now: it would re-tune every existing ranking
  and discard recency, confidence, usefulness, and access frequency, which are the product's ranking model. It is also
  a much larger change to defend without a gold set.
- **Union everything and let composite scoring decide** (no fusion). Rejected: composite relevance treats a full-text
  hit as `0.5`, so a full-text-only hit rarely outranks a vector hit on a full page — the sparse channel would remain
  unable to contribute, which is the defect being fixed.
- **Two-stage with a larger admitted window** (for example `2 × limit`). Kept as the fallback if the gold set shows the
  tighter window losing vector recall, but not the default: it would hydrate twice the page and make fusion decorative
  again, because composite score reorders the whole window.

## Consequences

- An exact-token or identifier match can enter the page even when the embedding ranks it outside the ANN top-k, and a
  hit both channels return outranks a hit only one returned.
- Retrieval now issues both queries. The full-text query keeps its GIN index path and its `LIMIT`, and the vector query
  is unchanged, but the read path performs two index probes instead of one when the flag is on.
- Hydration and the Tier-1 PII re-check operate on at most `limit` candidates, so the response cost stays bounded by the
  page size.
- Because fusion decides admission and composite decides order, the two stages can disagree: a memory admitted at fused
  rank 1 can be presented last. That is intentional — admission is a retrieval question, presentation is a ranking
  question — and it is why the flag is off until a measured comparison exists.
- The composite relevance floor can shorten a page that fusion filled, exactly as it could before this change.
- Default-on is gated on the phase 5.C.1 gold-set comparison. Until then this record stays **Proposed** and the status
  ledger makes no retrieval-quality claim.

## References

- Cormack, G. V., Clarke, C. L. A., and Büttcher, S. "Reciprocal Rank Fusion outperforms Condorcet and individual
  rank learning methods." SIGIR 2009.
- Elasticsearch `rrf` retriever, `rank_constant` default `60`
  (<https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html>).
- [ADR-0068](0068-composite-relevance-gate.md) — composite scoring weights, relevance floor, and the full-text sentinel.
- [ADR-0053](0053-vector-store-abstraction.md) — vector store abstraction and retrieval-time `min_similarity`.
- `engineering/API_DOCUMENTATION.md` § `POST /v1/memories/search` — the two retrieval modes and their observability.
