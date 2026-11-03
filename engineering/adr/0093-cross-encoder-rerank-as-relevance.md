---
title: "ADR-0093: Cross-encoder reranking replaces the relevance component, not the order"
description: "Architecture decision record 0093: an optional TEI cross-encoder reranks the fused hybrid window, its score becomes the composite relevance component, and any failure degrades to the fused order inside a hard latency stop."
adrId: "0093"
status: "Proposed"
date: "2026-11-03"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Proposed" date="2026-11-03" id="0093"}
::

# ADR-0093: Cross-encoder reranking replaces the relevance component, not the order

- **Status:** Proposed
- **Date:** 2026-11-03
- **Author:** Elshaday Mengesha (@Rick1330)
- **Related:** [ADR-0092](0092-hybrid-retrieval-rrf-admission.md), [ADR-0068](0068-composite-relevance-gate.md), [ADR-0061](0061-retrieval-quality-benchmark-methodology.md).
- **Implementation:** `services/memory/app/clients/rerank.py`, `services/memory/app/read/repository.py`, `services/memory/app/read/ranking.py`; milestone 5.A.3.

## Context

Hybrid retrieval (ADR-0092) produces a candidate window ordered by reciprocal rank fusion, and ADR-0068 composite
scoring decides the presented order from relevance, recency, usefulness, confidence, and access frequency.

The relevance component is still an approximation. A bi-encoder embeds the query and each memory independently, so it
cannot weigh a query term against a document term; a full-text hit has no cosine score at all and uses a fixed `0.5`
sentinel. A cross-encoder scores the `(query, document)` pair jointly and is the standard second stage of a two-stage
retriever: cheap retrieval first, expensive scoring on a bounded window.

The question this record settles is what a reranker is allowed to override.

## Decision

1. **Reranking is optional and off by default** (`IBEX_MEMORY_RERANK_ENABLED=false`). It only runs when hybrid
   retrieval is enabled; enabling it without hybrid logs a warning and does nothing.
2. **The reranker scores the fused window, never the corpus.** The window is the fused candidate list capped by
   `IBEX_MEMORY_RERANK_MAX_CANDIDATES` (default `50`), hydrated with the same tenant, lifecycle, and confidence fence as
   any other read.
3. **Its score replaces the composite relevance component.** Recency, usefulness, confidence, access frequency, the
   ADR-0068 weights, and the relevance floor keep their meaning. The reranker changes *how relevant* a memory is, not
   *how the page is ordered*.
4. **The HTTP response still reports retrieval provenance** (`source` = `vector` or `full_text`). The reranker is a
   scoring stage, not a third retrieval channel, and overloading `source` would misreport where a memory came from.
5. **A hard stop on the stage, then degrade.** One rerank *stage* per search, bounded by
   `IBEX_MEMORY_RERANK_TIMEOUT_MS` (default `100`) and zero retries by default. The stage is one `POST /rerank` when
   the window fits `IBEX_MEMORY_RERANK_CLIENT_BATCH_SIZE` (default `32`), and otherwise that many concurrent requests;
   all of them must succeed, because a partially scored window would rank rows against scores that never arrived. That
   cap bounds the stage, **not the request**: retrieval and hydration have already happened, and a degrade may hydrate
   more rows. Timeout, transport
   error, auth rejection, or a malformed response increments `ibex_memory_rerank_total{result="degraded"}` and returns
   the fused order. A slow reranker must never turn a search into an error; it can still cost latency, which is why the
   histogram exists and why enabling this is a measurement decision.
6. **Only a page the reranker empties falls back.** If every reranked score lands below the relevance floor, the
   request returns the fused ranking and records `result="emptied"`. A page that is merely shorter than `limit` keeps
   the reranked order — mixing reranked and unreranked relevance in one page would be worse than a short page.
7. **Blocked content never reaches the reranker.** The read-path Tier-1 PII guard runs before the documents are built,
   so a row the API would withhold is not sent to an inference endpoint either.

## Alternatives considered

- **Rerank as the final order** (the textbook two-stage shape). Rejected for now: it replaces ADR-0068 with a pure
  relevance sort and silently drops recency, confidence, usefulness, and access frequency from the product's ranking
  model. It is a bigger behavioural change than the one this milestone needs, and it would need its own ADR.
- **Rerank all hydrated candidates on every request** with no window cap. Rejected: cross-encoder cost is linear in
  documents and the reranker would see candidates fusion already rejected, so the extra time buys nothing.
- **Rerank before hydration** on ids only. Rejected: a cross-encoder needs the text, and hydrating first is what keeps
  the tenant and lifecycle fence identical to the rest of the read path.
- **Retries inside the read deadline.** Rejected as a default: a retry queue behind a slow model is worse than the fused
  order it degrades to. Operators who can afford it raise `IBEX_MEMORY_RERANK_MAX_RETRIES`.
- **Require the operator to raise TEI's `--max-client-batch-size`.** Rejected: the two defaults disagreed, and the
  disagreement was silent. A 50-candidate window against a stock server (limit `32`) returns `413`, which the read path
  correctly treats as "degrade", so rerank was a no-op on every default deployment while the counter said `degraded`
  and the page looked normal. The client now owns the split, so the window is independent of a server flag.
- **A new `reranker` wrapper service** in front of TEI. Deferred: the memory service talks to TEI's `POST /rerank`
  directly with the same client conventions as the embedder, and a wrapper adds a hop without adding a contract. Add one
  only if auth, caching, or provider abstraction needs it.

## Consequences

- Enabling rerank adds one network hop and one model inference per request to a searchable hybrid request, and a
  candidate window above `IBEX_MEMORY_RERANK_CLIENT_BATCH_SIZE` multiplies both (1..N concurrent `POST /rerank` calls);
  the stage is bounded, not each call. The rerank path hydrates a wider window before scoring (bounded by
  `IBEX_MEMORY_RERANK_MAX_CANDIDATES`). The stop bounds one stage, so a request can exceed the memory search p95 target
  when rerank is on; the histogram and the outcome counter are how that becomes visible instead of a mystery.
- The relevance floor now applies to a calibrated score. A cross-encoder can legitimately score an on-topic memory below
  `0.15`, which shortens or empties a page; a short page keeps the reranked order and an emptied one falls back to the
  fused order, so a floor surprise is a smaller page rather than an outage.
- `ts_rank_cd`'s fixed `0.5` composite sentinel no longer matters when rerank is on, because every admitted candidate
  gets a real relevance score. The sentinel remains the fallback behaviour.
- The reranker is a new external dependency on the read path. It is default-off, and its absence is a degrade, not a
  failure, so the service stays available without it.
- Default-on and any tuned window or timeout are measurement decisions. Phase 5.C.3 shadow evaluation and the
  retrieval-quality benchmark decide them; until then this record stays **Proposed** and no ranking-quality claim is
  made.

## References

- Hugging Face Text Embeddings Inference, `POST /rerank` request and response schema
  (<https://huggingface.github.io/text-embeddings-inference/#/Text%20Embeddings%20Inference/rerank>).
- `BAAI/bge-reranker-v2-m3`, multilingual cross-encoder reranker (XLM-RoBERTa base).
- [ADR-0092](0092-hybrid-retrieval-rrf-admission.md) — the fused window this stage consumes.
- [ADR-0068](0068-composite-relevance-gate.md) — composite weights, relevance floor, and the full-text sentinel.
- [ADR-0061](0061-retrieval-quality-benchmark-methodology.md) — the gold set and regression gate that must show a gain.
