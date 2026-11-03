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
5. **A hard latency stop, then degrade.** One rerank call per search, bounded by
   `IBEX_MEMORY_RERANK_TIMEOUT_MS` (default `100`, the memory search p95 target) and zero retries by default. Timeout,
   transport error, auth rejection, or a malformed response increments
   `ibex_memory_rerank_total{result="degraded"}` and returns the fused order. A slow reranker must never turn a search
   into an error or blow the read budget.
6. **A page the reranker empties falls back to the fused order.** If every reranked score lands below the relevance
   floor, the request returns the fused ranking rather than an empty page.

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
- **A new `reranker` wrapper service** in front of TEI. Deferred: the memory service talks to TEI's `POST /rerank`
  directly with the same client conventions as the embedder, and a wrapper adds a hop without adding a contract. Add one
  only if auth, caching, or provider abstraction needs it.

## Consequences

- Enabling rerank adds one network hop and one model inference to a searchable hybrid request. The hard stop bounds the
  added latency, but a reranker that routinely hits the stop degrades most requests — the histogram is how that becomes
  visible instead of a mystery.
- The relevance floor now applies to a calibrated score. A cross-encoder can legitimately score an on-topic memory below
  `0.15`, which shortens or empties a page; the fused-order fallback keeps that from becoming an outage.
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
