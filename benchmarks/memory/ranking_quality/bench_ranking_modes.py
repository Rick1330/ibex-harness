#!/usr/bin/env python3
"""Run the gold-set v2 corpus under every retrieval mode and score each one.

The scoring is deliberately separated from the retrieval driver:

* `score_mode` is pure — it takes, per query, the ranked ids a mode produced and the relevance
  grades, and returns overall / non-graph / graph nDCG plus the per-subset counts the gate
  validates. That makes the arithmetic testable without a database, a reranker, or a clock.
* `run_mode` is the thin async shell that asks the repository for a page per query under one
  mode's settings. Everything mode-specific lives in `modes.py`; this file never branches on a
  mode name.

The split matters because a benchmark whose *scoring* is untestable is a benchmark nobody can
trust — the interesting failures (wrong subset, wrong k, unjudged documents counted as relevant)
live in the arithmetic, not in the loop.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RANK_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _RANK_DIR.parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _BENCH_MEMORY, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gate_modes import ModeResult
from validate_gold_set_v2 import GOLD_SET_NAME

try:  # the service package is only needed by the live driver, not by the scoring tests
    from app.eval.ranking import ndcg_at_k
except ModuleNotFoundError:  # pragma: no cover - exercised only when run without the venv
    ndcg_at_k = None  # type: ignore[assignment]

OUTPUT_DIR = _RANK_DIR / "output"
TOP_K = 10
GRAPH_SUBSET = "graph"
# The two groups the gate compares. Dense and lexical answers are the "non-graph" side: they are
# what reranking is supposed to improve, and the graph queries are what suppression is supposed
# to improve. Averaging them together would hide both.
NON_GRAPH_SUBSETS = frozenset({"dense", "lexical"})
# Fixed order so the published artifact is byte-reproducible across runs.
SUBSET_ORDER = ("dense", "lexical", "graph")


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """What one mode returned for one query."""

    query_id: str
    subset: str
    ranked_ids: Sequence[str]
    expected_ids: Sequence[str]


def grades_from_expected(expected_ids: Sequence[str]) -> dict[str, float]:
    """Gold-set v2 labels are binary per query: the expected ids are the relevant ones.

    Grading the expectations at 1.0 rather than inventing 2 or 3 keeps the number honest: the
    corpus states which memories answer the query, not how good each one is. When the labelers
    add graded judgments (5.C.1c) this is the one place that has to change.
    """
    return {memory_id: 1.0 for memory_id in expected_ids}


def score_mode(outcomes: Iterable[QueryOutcome]) -> ModeResult:
    """Aggregate one mode's per-query outcomes into the numbers the gate consumes."""
    if ndcg_at_k is None:  # pragma: no cover
        raise RuntimeError("the memory service package is required to score a run")

    per_subset: dict[str, list[float]] = {subset: [] for subset in SUBSET_ORDER}
    overall: list[float] = []
    seen: set[str] = set()
    for outcome in outcomes:
        if outcome.subset not in per_subset:
            raise ValueError(f"unknown subset {outcome.subset!r} on {outcome.query_id!r}")
        if outcome.query_id in seen:
            # A repeated row would be weighted twice and the gate's counts invariant would
            # still hold, so nothing downstream could notice.
            raise ValueError(f"duplicate query_id {outcome.query_id!r}")
        seen.add(outcome.query_id)
        if not outcome.expected_ids:
            # An unresolved gold key looks exactly like a total miss. Scoring it 0.0 would drag
            # the published number down with no diagnostic.
            raise ValueError(f"{outcome.query_id!r} has no expected ids; resolve the gold keys")
        score = ndcg_at_k(list(outcome.ranked_ids), grades_from_expected(outcome.expected_ids), TOP_K)
        per_subset[outcome.subset].append(score)
        overall.append(score)

    return ModeResult(
        mode="",  # filled by the caller that knows which mode ran
        overall=_mean(overall),
        non_graph=_mean([s for subset in NON_GRAPH_SUBSETS for s in per_subset[subset]]),
        graph=_mean(per_subset[GRAPH_SUBSET]),
        query_count=len(overall),
        per_subset_counts={subset: len(scores) for subset, scores in per_subset.items()},
    )


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def with_mode(result: ModeResult, mode: str) -> ModeResult:
    return ModeResult(
        mode=mode,
        overall=result.overall,
        non_graph=result.non_graph,
        graph=result.graph,
        query_count=result.query_count,
        per_subset_counts=result.per_subset_counts,
    )


def build_payload(
    results: Mapping[str, ModeResult],
    *,
    gold_set: str,
    top_k: int = TOP_K,
    reranker: str,
) -> dict[str, Any]:
    """The published artifact. Every number carries the definitions that produced it."""
    return {
        "schema_version": 2,
        "benchmark": "ranking_quality",
        "gold_set": gold_set,
        "top_k": top_k,
        "reranker": reranker,
        "modes": {
            name: {
                "ndcg_at_10": round(result.overall, 6),
                "non_graph_ndcg_at_10": round(result.non_graph, 6),
                "graph_ndcg_at_10": round(result.graph, 6),
                "query_count": result.query_count,
                "per_subset_counts": dict(result.per_subset_counts),
            }
            for name, result in sorted(results.items())
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Score a recorded run and write the artifact.

    The live driver needs Postgres, pgvector, and the seeded corpus; it is wired separately so
    this entry point can be exercised from a recorded result file in CI and in tests.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True, help="recorded per-query outcomes")
    parser.add_argument("--gold-set", default=GOLD_SET_NAME)
    parser.add_argument("--reranker", default="stub/lexical-overlap@1")
    args = parser.parse_args(argv[1:] if argv else None)

    recorded = json.loads(args.outcomes.read_text(encoding="utf-8"))
    results: dict[str, ModeResult] = {}
    for mode_name, outcomes in recorded["modes"].items():
        scored = score_mode(
            QueryOutcome(
                query_id=outcome["query_id"],
                subset=outcome["subset"],
                ranked_ids=outcome["ranked_ids"],
                expected_ids=outcome["expected_ids"],
            )
            for outcome in outcomes
        )
        results[mode_name] = with_mode(scored, mode_name)

    payload = build_payload(results, gold_set=args.gold_set, reranker=args.reranker)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / "modes-latest.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.name}: {len(payload['modes'])} modes over {payload['gold_set']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
