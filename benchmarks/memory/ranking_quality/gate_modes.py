"""Point-based gate for the multi-mode ranking benchmark.

The v1 gate compared percentages with a 5 % tolerance, which hides exactly the regressions this
track exists to catch: at a score near 1.0, 5 % is nothing, and a mode can lose several points of
nDCG while staying inside it. ADR-0061's own consequences section says the same thing.

So the gate is absolute points against a committed baseline, plus one relative comparison that no
absolute floor can express: the graph-aware mode must not give back what reranking bought on the
queries that are *not* about the graph.

Every number here is a fraction in ``[0, 1]``; the policy is in points, because that is how a
reader thinks about a score drop ("three points of nDCG").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

# A mode may not fall more than this many points below its committed baseline.
MAX_DROP_POINTS: Final = 3.0
# full_graph must stay within this many points of hybrid_rerank on non-graph queries.
MAX_GRAPH_GAP_POINTS: Final = 2.0
# Below this many evaluated queries a subset's mean is noise, not a measurement.
MIN_QUERIES_PER_SUBSET: Final = 10
# Subset name used by the corpus for the queries the graph mode is meant to move.
GRAPH_SUBSET: Final = "graph"
POINTS: Final = 100.0
# Scores are fractions, so a point comparison needs slack well below published precision.
_EPSILON: Final = 1e-9


@dataclass(frozen=True, slots=True)
class ModeResult:
    """One mode's scores on one corpus."""

    mode: str
    overall: float
    non_graph: float
    graph: float
    query_count: int
    per_subset_counts: Mapping[str, int]

    def score_for(self, subset: str) -> float:
        """Score for a named subset; an unknown name is an error, not the graph score."""
        try:
            return _SUBSET_FIELDS[subset]
        except KeyError:
            raise ValueError(f"unknown subset {subset!r}") from None

    def _score_for_field(self, subset: str) -> float:
        field = _SUBSET_FIELDS[subset]
        return getattr(self, "overall" if field == "overall" else field)


_SUBSET_FIELDS: Final = {"overall": "overall", "non_graph": "non_graph", "graph": "graph"}


@dataclass(frozen=True, slots=True)
class GateFailure:
    mode: str
    check: str
    detail: str

    def render(self) -> str:
        return f"[{self.mode}] {self.check}: {self.detail}"


def evaluate_gate(
    results: Mapping[str, ModeResult],
    baseline: Mapping[str, float],
    *,
    reference_mode: str = "hybrid_rerank",
    subject_mode: str = "full_graph",
    max_drop_points: float = MAX_DROP_POINTS,
    max_gap_points: float = MAX_GRAPH_GAP_POINTS,
    min_queries: int = MIN_QUERIES_PER_SUBSET,
) -> list[GateFailure]:
    """Return every failing check; an empty list means the gate passes."""
    failures: list[GateFailure] = [*_validate_coverage(results, baseline)]
    failures.extend(_validate_shapes(results, min_queries))
    if failures:
        return failures
    failures.extend(_check_baseline_drops(results, baseline, max_drop_points))
    failures.extend(_check_graph_gap(results, reference_mode, subject_mode, max_gap_points))
    return failures


def _validate_coverage(
    results: Mapping[str, ModeResult],
    baseline: Mapping[str, float],
) -> list[GateFailure]:
    """A baseline with no result means the run did not produce what it promised.

    Skipping the comparison instead — which is what a missing mode used to do — turns the gate
    green for the exact run that failed to measure the thing it exists to measure.
    """
    if not results:
        return [GateFailure(mode="-", check="coverage", detail="no mode produced a result")]
    return [
        GateFailure(
            mode=name,
            check="coverage",
            detail="committed baseline has no result for this mode; the run did not measure it",
        )
        for name in sorted(baseline)
        if name not in results
    ]


def _validate_shapes(
    results: Mapping[str, ModeResult],
    min_queries: int,
) -> list[GateFailure]:
    """A subset too small, or a score outside [0, 1], makes every other check meaningless."""
    failures: list[GateFailure] = []
    for name, result in results.items():
        failures.extend(_validate_scores(name, result))
        failures.extend(_validate_subset_counts(name, result, min_queries))
        if result.query_count < min_queries:
            failures.append(
                GateFailure(
                    mode=name,
                    check="corpus size",
                    detail=(
                        f"{result.query_count} queries is below the {min_queries} needed for a "
                        "mean worth publishing"
                    ),
                )
            )
    return failures


def _validate_subset_counts(
    name: str,
    result: ModeResult,
    min_queries: int,
) -> list[GateFailure]:
    """A subset with too few queries reports a mean that is noise, not a measurement."""
    failures = [
        GateFailure(
            mode=name,
            check="subset size",
            detail=f"{subset} was scored on {count} queries, below the {min_queries} required",
        )
        for subset, count in sorted(result.per_subset_counts.items())
        if subset != GRAPH_SUBSET and count < min_queries
    ]
    total = sum(result.per_subset_counts.values())
    if result.per_subset_counts and total != result.query_count:
        failures.append(
            GateFailure(
                mode=name,
                check="subset size",
                detail=f"subset counts sum to {total} but query_count is {result.query_count}",
            )
        )
    return failures


def _validate_scores(name: str, result: ModeResult) -> list[GateFailure]:
    return [
        GateFailure(mode=name, check="score range", detail=f"{field} is {value}, outside [0, 1]")
        for field, value in (
            ("overall", result.overall),
            ("non_graph", result.non_graph),
            ("graph", result.graph),
        )
        if not 0.0 <= value <= 1.0
    ]


def _check_baseline_drops(
    results: Mapping[str, ModeResult],
    baseline: Mapping[str, float],
    max_drop_points: float,
) -> list[GateFailure]:
    failures: list[GateFailure] = []
    for name, result in results.items():
        if name not in baseline:
            failures.append(
                GateFailure(
                    mode=name,
                    check="baseline",
                    detail="no committed baseline for this mode; publish one before gating on it",
                )
            )
            continue
        drop_points = (baseline[name] - result.overall) * POINTS
        if drop_points > max_drop_points + _EPSILON:
            failures.append(
                GateFailure(
                    mode=name,
                    check="baseline drop",
                    detail=(
                        f"{result.overall:.4f} is {drop_points:.2f} points below the "
                        f"{baseline[name]:.4f} baseline (max {max_drop_points:.1f})"
                    ),
                )
            )
    return failures


def _check_graph_gap(
    results: Mapping[str, ModeResult],
    reference_mode: str,
    subject_mode: str,
    max_gap_points: float,
) -> list[GateFailure]:
    """The comparison the milestone is about.

    A missing mode is not a failure here: the runner skips modes the service cannot run yet, and
    the shape check already reports a baseline with no result. Only a *measured* pair can fail
    this one.
    """
    reference = results.get(reference_mode)
    subject = results.get(subject_mode)
    if reference is None or subject is None:
        return []
    gap_points = (reference.non_graph - subject.non_graph) * POINTS
    # Float subtraction makes an exactly-at-allowance gap land a hair over it.
    if gap_points <= max_gap_points + _EPSILON:
        return []
    return [
        GateFailure(
            mode=subject_mode,
            check="graph gap",
            detail=(
                f"non-graph nDCG {subject.non_graph:.4f} trails {reference_mode} "
                f"({reference.non_graph:.4f}) by {gap_points:.2f} points, over the "
                f"{max_gap_points:.1f}-point allowance"
            ),
        )
    ]


def render_report(
    results: Mapping[str, ModeResult],
    failures: list[GateFailure],
    baseline: Mapping[str, float],
) -> str:
    """A Markdown table a human can read in the PR without opening the JSON."""
    lines = [
        "| mode | overall | non-graph | graph | vs baseline (pts) |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(results):
        result = results[name]
        delta = (
            f"{(result.overall - baseline[name]) * POINTS:+.2f}"
            if name in baseline
            else "no baseline"
        )
        lines.append(
            f"| {name} | {result.overall:.4f} | {result.non_graph:.4f} | "
            f"{result.graph:.4f} | {delta} |"
        )
    lines.append("")
    if failures:
        lines.append(f"Gate failed ({len(failures)}):")
        lines.extend(f"- {failure.render()}" for failure in failures)
    else:
        lines.append("Gate passed.")
    return "\n".join(lines)
