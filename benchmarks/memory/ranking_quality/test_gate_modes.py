"""Tests for the multi-mode gate: absolute points, and the graph-gap comparison."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_RANK_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gate_modes import ModeResult, evaluate_gate, render_report
from modes import (
    MODE_BY_NAME,
    MODES,
    UnsupportedModeError,
    modes_with_suppression_support,
    require_supported,
)


def _result(mode: str, **scores: Any) -> ModeResult:
    """Build a result from keyword scores; ``counts``/``total`` override the corpus shape."""
    counts = scores.pop("counts", None) or {"dense": 60, "lexical": 50, "graph": 40}
    total = scores.pop("total", None)
    return ModeResult(
        mode=mode,
        overall=scores["overall"],
        non_graph=scores["non_graph"],
        graph=scores["graph"],
        query_count=sum(counts.values()) if total is None else total,
        per_subset_counts=counts,
    )


def _healthy() -> dict[str, ModeResult]:
    return {
        "dense_only": _result("dense_only", overall=0.62, non_graph=0.60, graph=0.68),
        "hybrid": _result("hybrid", overall=0.71, non_graph=0.70, graph=0.74),
        "hybrid_rerank": _result("hybrid_rerank", overall=0.80, non_graph=0.79, graph=0.83),
        "full_graph": _result("full_graph", overall=0.80, non_graph=0.78, graph=0.86),
    }


def _has_suppression_field(base: object) -> bool:
    return "conflict_suppression_enabled" in type(base).model_fields


BASELINE = {"dense_only": 0.62, "hybrid": 0.71, "hybrid_rerank": 0.80, "full_graph": 0.80}


class TestModes:
    def test_every_mode_is_named_once(self) -> None:
        assert [mode.name for mode in MODES] == [
            "dense_only",
            "hybrid",
            "hybrid_rerank",
            "full_graph",
        ]
        assert set(MODE_BY_NAME) == {mode.name for mode in MODES}

    def test_dense_only_disables_the_phase5_stages(self) -> None:
        from app.config import Settings

        # Start from a base where both stages are on, or the assertion proves nothing.
        base = Settings(search_hybrid_enabled=True, rerank_enabled=True, search_fallback_enabled=True)
        settings = MODE_BY_NAME["dense_only"].settings_for(base)

        assert settings.search_hybrid_enabled is False
        assert settings.rerank_enabled is False

    def test_dense_only_cannot_be_refilled_with_full_text_hits(self) -> None:
        from app.config import Settings

        base = Settings(search_fallback_enabled=True)
        settings = MODE_BY_NAME["dense_only"].settings_for(base)

        assert settings.search_fallback_enabled is False

    def test_hybrid_rerank_enables_both_stages(self) -> None:
        from app.config import Settings

        settings = MODE_BY_NAME["hybrid_rerank"].settings_for(Settings())

        assert settings.search_hybrid_enabled is True
        assert settings.rerank_enabled is True

    def test_a_mode_changes_nothing_outside_its_delta(self) -> None:
        from app.config import Settings

        base = Settings(composite_relevance_floor=0.2, search_rrf_k=42)

        for mode in MODES:
            if mode.conflict_suppression and not _has_suppression_field(base):
                continue
            settings = mode.settings_for(base)
            assert settings.composite_relevance_floor == pytest.approx(0.2)
            assert settings.search_rrf_k == 42

    def test_full_graph_is_refused_while_the_switch_is_missing(self) -> None:
        from app.config import Settings

        base = Settings(conflict_suppression_enabled=True) if hasattr(
            Settings(), "conflict_suppression_enabled"
        ) else Settings()

        if hasattr(base, "conflict_suppression_enabled"):
            pytest.skip("the service already exposes the suppression switch")

        with pytest.raises(UnsupportedModeError, match="conflict_suppression_enabled"):
            require_supported(MODE_BY_NAME["full_graph"], base)

    def test_runnable_modes_drop_the_unsupported_one(self) -> None:
        from app.config import Settings

        base = Settings()
        expected = {"dense_only", "hybrid", "hybrid_rerank"}
        if hasattr(base, "conflict_suppression_enabled") and base.conflict_suppression_enabled is None:
            expected.add("full_graph")

        assert {mode.name for mode in modes_with_suppression_support(base)} == expected


class TestGate:
    def test_healthy_results_pass(self) -> None:
        assert evaluate_gate(_healthy(), BASELINE) == []

    def test_a_mode_more_than_three_points_below_baseline_fails(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.67, non_graph=0.66, graph=0.70)

        failures = evaluate_gate(results, BASELINE)

        assert [f.check for f in failures] == ["baseline drop"]
        assert "4.00 points below" in failures[0].detail

    def test_exactly_three_points_below_still_passes(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.68, non_graph=0.67, graph=0.71)

        assert evaluate_gate(results, BASELINE) == []

    def test_graph_mode_trailing_rerank_on_non_graph_queries_fails(self) -> None:
        results = _healthy()
        results["full_graph"] = _result("full_graph", overall=0.78, non_graph=0.70, graph=0.92)

        failures = evaluate_gate(results, BASELINE)

        assert [f.check for f in failures] == ["graph gap"]
        assert "9.00 points" in failures[0].detail

    def test_the_graph_gap_allowance_is_inclusive(self) -> None:
        results = _healthy()
        results["full_graph"] = _result("full_graph", overall=0.80, non_graph=0.77, graph=0.86)

        assert evaluate_gate(results, BASELINE) == []

    def test_graph_subset_is_not_part_of_the_gap_comparison(self) -> None:
        # full_graph gives back nothing on non-graph queries; a worse graph score is the thing
        # the mode is meant to change, so it must not fail this check.
        results = _healthy()
        results["full_graph"] = _result("full_graph", overall=0.78, non_graph=0.79, graph=0.60)

        assert evaluate_gate(results, BASELINE) == []

    def test_a_missing_baseline_fails_loudly(self) -> None:
        results = _healthy()
        partial = {name: value for name, value in BASELINE.items() if name != "full_graph"}

        failures = evaluate_gate(results, partial)

        assert [f.check for f in failures] == ["baseline"]

    def test_a_score_outside_the_unit_interval_fails(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=1.4, non_graph=0.7, graph=0.7)

        failures = evaluate_gate(results, BASELINE)

        assert failures[0].check == "score range"

    def test_a_corpus_too_small_to_publish_fails(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.71, non_graph=0.70, graph=0.74, counts={"dense": 2, "lexical": 2, "graph": 1})

        failures = evaluate_gate(results, BASELINE)

        assert "corpus size" in {f.check for f in failures}

    def test_report_names_every_mode_and_the_verdict(self) -> None:
        results = _healthy()

        report = render_report(results, [], BASELINE)

        assert "| mode |" in report
        for name in results:
            assert name in report
        assert "Gate passed." in report

    def test_a_result_missing_from_the_run_fails(self) -> None:
        # The mode this milestone is about must not vanish silently.
        results = _healthy()
        del results["full_graph"]

        failures = evaluate_gate(results, BASELINE)

        assert [f.check for f in failures] == ["coverage"]
        assert "full_graph" in failures[0].render()

    def test_an_empty_run_fails(self) -> None:
        assert evaluate_gate({}, {})[0].check == "coverage"

    def test_a_subset_too_small_fails_even_when_the_total_is_large(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=0.71, non_graph=0.70, graph=0.74,
            counts={"dense": 60, "lexical": 5, "graph": 40},
        )

        assert "subset size" in {f.check for f in evaluate_gate(results, BASELINE)}

    def test_subset_counts_must_sum_to_the_total(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=0.71, non_graph=0.70, graph=0.74,
            counts={"dense": 60, "lexical": 50, "graph": 10}, total=150,
        )

        assert "subset size" in {f.check for f in evaluate_gate(results, BASELINE)}

    def test_unknown_subset_name_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="unknown subset"):
            _healthy()["hybrid"].score_for("dense")


    def test_report_lists_failures(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.60, non_graph=0.60, graph=0.60)

        failures = evaluate_gate(results, BASELINE)
        report = render_report(results, failures, BASELINE)

        assert "Gate failed" in report
        assert "baseline drop" in report


