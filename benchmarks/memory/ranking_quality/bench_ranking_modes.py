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
except (
    ModuleNotFoundError
):  # pragma: no cover - exercised only when run without the venv
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
    return dict.fromkeys(expected_ids, 1.0)


def validate_outcomes(outcomes: Iterable[QueryOutcome]) -> list[QueryOutcome]:
    """Reject the rows that would make a score quietly wrong, before any arithmetic runs.

    Kept separate from `score_mode` so the scoring loop stays a loop: every rule here exists
    because the failure it prevents is invisible downstream.
    """
    validated: list[QueryOutcome] = []
    seen: set[str] = set()
    for outcome in outcomes:
        if outcome.subset not in SUBSET_ORDER:
            raise ValueError(
                f"unknown subset {outcome.subset!r} on {outcome.query_id!r}"
            )
        if outcome.query_id in seen:
            # A repeated row would be weighted twice and the gate's counts invariant would
            # still hold, so nothing downstream could notice.
            raise ValueError(f"duplicate query_id {outcome.query_id!r}")
        if not outcome.expected_ids:
            # An unresolved gold key looks exactly like a total miss. Scoring it 0.0 would drag
            # the published number down with no diagnostic.
            raise ValueError(
                f"{outcome.query_id!r} has no expected ids; resolve the gold keys"
            )
        seen.add(outcome.query_id)
        validated.append(outcome)
    return validated


def score_mode(outcomes: Iterable[QueryOutcome]) -> ModeResult:
    """Aggregate one mode's per-query outcomes into the numbers the gate consumes."""
    if ndcg_at_k is None:  # pragma: no cover
        raise RuntimeError("the memory service package is required to score a run")

    validated = validate_outcomes(outcomes)
    per_subset: dict[str, list[float]] = {subset: [] for subset in SUBSET_ORDER}
    overall: list[float] = []
    for outcome in validated:
        score = ndcg_at_k(
            list(outcome.ranked_ids), grades_from_expected(outcome.expected_ids), TOP_K
        )
        per_subset[outcome.subset].append(score)
        overall.append(score)

    return ModeResult(
        mode="",  # filled by the caller that knows which mode ran
        overall=_mean(overall),
        non_graph=_mean(
            [s for subset in NON_GRAPH_SUBSETS for s in per_subset[subset]]
        ),
        graph=_mean(per_subset[GRAPH_SUBSET]),
        query_count=len(overall),
        per_subset_counts={
            subset: len(scores) for subset, scores in per_subset.items()
        },
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


def _parse_outcomes(mode: str, rows: Sequence[Mapping[str, Any]]) -> list[QueryOutcome]:
    """Turn one mode's recorded rows into outcomes, naming the bad row when one is malformed."""
    outcomes: list[QueryOutcome] = []
    for index, row in enumerate(rows):
        try:
            outcomes.append(
                QueryOutcome(
                    query_id=row["query_id"],
                    subset=row["subset"],
                    ranked_ids=tuple(row["ranked_ids"]),
                    expected_ids=tuple(row["expected_ids"]),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"mode {mode!r} row {index} is missing {exc.args[0]!r}"
            ) from exc
        except TypeError as exc:
            raise ValueError(
                f"mode {mode!r} row {index} is not a mapping: {exc}"
            ) from exc
    return outcomes


def assert_comparable(modes: Mapping[str, Sequence[QueryOutcome]]) -> None:
    """Every mode must be scored on the same queries, with the same gold expectations.

    The gate compares modes against each other, so a mode that silently dropped its hard
    queries would report a better mean while still clearing the per-subset minimum-count
    check. Cross-checking the gold keys is the only thing that catches that.
    """
    gold: dict[str, tuple[str, tuple[str, ...]]] | None = None
    baseline = ""
    for name, outcomes in modes.items():
        keys = {o.query_id: (o.subset, tuple(sorted(o.expected_ids))) for o in outcomes}
        if gold is None:
            gold, baseline = keys, name
            continue
        problems = _comparability_problems(gold, keys)
        if problems:
            raise ValueError(
                f"mode {name!r} is not comparable to {baseline!r}: "
                + "; ".join(problems)
            )


def _comparability_problems(
    gold: Mapping[str, tuple[str, tuple[str, ...]]],
    keys: Mapping[str, tuple[str, tuple[str, ...]]],
) -> list[str]:
    missing = sorted(set(gold) - set(keys))
    extra = sorted(set(keys) - set(gold))
    differing = sorted(q for q in set(gold) & set(keys) if gold[q] != keys[q])
    problems: list[str] = []
    if missing:
        problems.append(f"missing {len(missing)} queries ({_preview(missing)})")
    if extra:
        problems.append(
            f"scored {len(extra)} queries the baseline did not ({_preview(extra)})"
        )
    if differing:
        problems.append(
            f"{len(differing)} queries differ in subset or expectations ({_preview(differing)})"
        )
    return problems


def _preview(ids: Sequence[str], limit: int = 3) -> str:
    shown = ", ".join(ids[:limit])
    return f"{shown}{', …' if len(ids) > limit else ''}"


def load_recorded(path: Path) -> dict[str, list[QueryOutcome]]:
    """Read a recorded run and refuse one whose modes are not scored on the same queries.

    The path is the operator's own CLI argument: this runs with the invoking user's privileges,
    on a file that user named, so there is no boundary to traverse, and the CI invocation passes
    a temp file it just wrote. NOSONAR records that here rather than leaving a gate nobody can
    explain; the alternative -- confining reads to one directory -- would only break callers.
    """
    # On its own line so the suppression marker sits on the statement Sonar reports.
    raw = path.read_text(encoding="utf-8")  # NOSONAR
    recorded = json.loads(raw)

    modes = recorded.get("modes") if isinstance(recorded, Mapping) else None
    if not isinstance(modes, Mapping) or not modes:
        raise ValueError(f"{path} has no modes to score")
    parsed = {name: _parse_outcomes(name, rows) for name, rows in modes.items()}
    assert_comparable(parsed)
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Score a recorded run and write the artifact.

    The live driver needs Postgres, pgvector, and the seeded corpus; it is wired separately so
    this entry point can be exercised from a recorded result file in CI and in tests.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outcomes", type=Path, required=True, help="recorded per-query outcomes"
    )
    parser.add_argument("--gold-set", default=GOLD_SET_NAME)
    parser.add_argument("--reranker", default="stub/lexical-overlap@1")
    args = parser.parse_args(argv[1:] if argv else None)

    recorded = load_recorded(args.outcomes)
    results = {
        name: with_mode(score_mode(outcomes), name)
        for name, outcomes in recorded.items()
    }

    payload = build_payload(results, gold_set=args.gold_set, reranker=args.reranker)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / "modes-latest.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {target.name}: {len(payload['modes'])} modes over {payload['gold_set']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
