---
title: "ADR-0095: Retrieval and labelling metrics are defined in code, once"
description: "Architecture decision record 0095: nDCG@k with exponential gain, tail-extrapolated RBO for rank shift, and Cohen's kappa with its confusion matrix live in services/memory/app/eval so the benchmark and the shadow path report the same numbers."
adrId: "0095"
status: "Accepted, partially wired"
date: "2026-11-03"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted, partially wired" date="2026-11-03" id="0095"}
::

# ADR-0095: Retrieval and labelling metrics are defined in code, once

- **Status:** Accepted, partially wired. The module exists — `services/memory/app/eval/ranking.py` (`ndcg_at_k`, `rbo`, `top1_agreement`), `services/memory/app/eval/agreement.py` (`cohen_kappa`, `KappaResult`), re-exported by `services/memory/app/eval/__init__.py` — and the benchmark imports it (`benchmarks/memory/ranking_quality/bench_ranking_modes.py`:44 imports `ndcg_at_k`). The agreement half has no importer outside a unit test (`services/memory/tests/unit/test_eval_agreement_unit.py`:7), and the shadow comparison (`5.C.3`) the decision names has no emitter in `services/memory/app` or `services/worker/app`; `app/eval/__init__.py` describes it in prose only. So the definitions are accepted and used where they are wired; the shadow path is not.
- **Date:** 2026-11-03
- **Authors:** Elshaday Mengesha (@Rick1330)
- **Milestone:** [5.C.1 Hybrid-aware gold set v2](/roadmap)

## Context

Phase 5 Track C needs three numbers that do not exist yet:

1. a **graded** quality score for one ranking (the v1 gold set only ever computed set-overlap metrics);
2. a **rank-shift** score between two rankings, for shadow comparison on traffic nobody labelled;
3. an **agreement** statistic for two labelers, because the gold set claims two independent labelers and a
   `kappa >= 0.8` gate.

The existing `benchmarks/memory/ranking_quality/metrics.py` covers precision@k, recall@k, MRR, and an order match. None
of those can express "the highly relevant memory moved from rank 1 to rank 3", and none can compare a live page against a
candidate page without a shared judged set. Two further constraints decide where the new code lives:

- the shadow comparison (5.C.3) runs inside the memory service, so it cannot import from `benchmarks/`;
- if the benchmark and the shadow path each define "divergence", a published quality number and a published divergence
  number stop being comparable, and a later reader cannot tell which definition produced either.

## Decision

1. **One module, in the service.** `services/memory/app/eval/` holds the definitions. The ranking benchmark already puts
   `services/memory` on `PYTHONPATH`, so 5.C.2 switches its imports to this module and retires the v1
   `benchmarks/.../metrics.py` in the same change; the two coexist only until that switch, never as a permanent second
   definition.
2. **Quality is nDCG@k with exponential gain** (`2**rel - 1`), a `log2(i+1)` discount, and normalisation by the ideal
   ordering. A document absent from the judgment map scores gain `0` — the pooled-judgment convention. An all-zero ideal
   scores `0.0`, not `1.0`, because a perfect score must mean "found what was worth finding".
3. **Rank shift is RBO@k with a tail term** (`p = 0.9` by default). The plain truncated sum tops out at `1 - p**k`
   (≈ `0.65` for a ten-item page), so identical pages would score `0.65` and every divergence report would carry a
   constant offset. Adding `p**k * A_k` makes identical rankings score `1.0` and disjoint rankings `0.0`.
   Rankings must be duplicate-free, and an empty page returns `1.0` only when both pages are empty.
4. **The change users notice is reported separately.** `top1_agreement` returns `1.0` when both rankings put the same
   document first, `0.0` otherwise, and `0.0` when either page is empty. It is published beside RBO because a page can
   keep its overall quality and still change its top hit, and that is the change a user feels; a single blended number
   would hide which of the two moved.
5. **Agreement is Cohen's kappa, reported with its confusion matrix and the raw observed agreement.** When both raters
   used a single identical category, kappa is `0/0` and is returned as `None` rather than `1.0`, so a degenerate design
   cannot pass the gate.
6. **No new dependency.** The formulas are short, and the definition *is* the deliverable; a package would move the
   definition somewhere a reviewer has to go and read, and would still need the same reference tests.
7. **Published numbers name their definition.** Any figure produced from these functions states the metric, `k`, and
   `p` beside it. A bare "nDCG" or "divergence" is not a number a reader can check.

## Alternatives rejected

- **Return a clamped score for a malformed page.** Rejected: a repeated id credits one judgment twice, so the raw ratio
  exceeds `1.0` and the clamp would report a perfect page. Duplicate-free rankings are required by both `ndcg_at_k` and
  `rbo`, and a repeated id raises.
- **Use an IR library (`ir_measures`, `pytrec_eval`, `rbo`).** Rejected: `pytrec_eval` is a C++ build, `rbo` is one
  person's implementation of an unambiguous formula, and all three would still need the same hand-computed reference
  tests. The three functions implemented here total about 120 statements. The reference values used to validate them
  come from the formula and, where a published value exists, from the paper's own worked examples.
- **Keep set-overlap metrics and add nothing.** Rejected: precision@k cannot distinguish a graded gold set from a binary
  one, which is the entire point of gold set v2, and it gives no signal at all when both rankings contain the same
  documents in a different order.
- **Use Pearson/Spearman correlation for rank shift.** Rejected: both need the same document set in both rankings and are
  not top-weighted; a page whose tail differs would look as bad as one whose top differs.
- **Use Krippendorff's alpha instead of kappa.** Not adopted now: the milestone gate is pre-registered on kappa, and
  swapping the statistic after seeing the labels would be moving the goalposts. Alpha remains the better statistic for
  skewed or missing-data designs; if the two-labeler run shows a prevalence problem, that becomes its own record rather
  than a silent change.
- **Report kappa alone.** Rejected: kappa is prevalence-sensitive (Feinstein & Cicchetti, 1990). The confusion matrix and
  observed agreement are returned in the same result object so a reviewer can see when the statistic is measuring skew.
- **Return `1.0` for the undefined single-category case.** Rejected: it converts "the protocol produced no information"
  into "perfect agreement".

## Consequences

- The benchmark and the shadow emitter compute identical numbers by construction, including the `p` and `k` defaults.
- The tail term makes RBO's boundary behaviour mechanical: identical `1.0`, disjoint `0.0`, and the value is monotone in
  the depth of agreement rather than scaled by an arbitrary constant.
- nDCG needs graded judgments to be worth anything. Until gold set v2 lands, the graded path is exercised only by tests;
  this record does not claim a measured quality improvement.
- Interpreting kappa still requires judgement. The protocol (5.C.1c) has to state how many items were double-labelled,
  which categories existed, and what the confusion matrix looked like — a kappa with no matrix is not evidence.
- These functions are pure and cheap, but they are not free on a hot path: the shadow emitter must bound how often it
  computes RBO, which 5.C.3 handles with sampling rather than by weakening the metric.

## References

- Webber, Moffat & Zobel, "A similarity measure for indefinite rankings", ACM TOIS 28(4), 2010 — RBO, including the
  prefix-weighted definition and the extrapolation used for the tail term.
- Järvelin & Kekäläinen, "Cumulated gain-based evaluation of IR techniques", ACM TOIS 20(4), 2002 — DCG/nDCG; the
  exponential gain variant follows the later standardisation.
- Cohen, "A coefficient of agreement for nominal scales", Educational and Psychological Measurement 20(1), 1960.
- Feinstein & Cicchetti, "High agreement but low kappa", Journal of Clinical Epidemiology 43(6), 1990 — the prevalence
  paradox that motivates reporting the matrix beside the statistic.
- [ADR-0061](0061-retrieval-quality-benchmark-methodology.md) — the benchmark methodology this extends.
- [ADR-0093](0093-cross-encoder-rerank-as-relevance.md) — the rerank stage whose effect these metrics measure.
