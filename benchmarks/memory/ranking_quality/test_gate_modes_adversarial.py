"""Adversarial tests for the multi-mode gate and the mode deltas.

These are written from the contract, not from the implementation:

* a mode's committed baseline must be matched by a result, and a result must have a baseline;
* every published score must rest on at least ``MIN_QUERIES_PER_SUBSET`` evaluated queries, and
  the subset counts must account for the whole corpus;
* a mode may not fall more than 3 points below its baseline, and ``full_graph`` may not trail
  ``hybrid_rerank`` by more than 2 points on non-graph queries — the comparison the milestone
  exists for, so it must not be possible to make it disappear;
* a mode is a delta over ``Settings`` and nothing else, and a mode that declares conflict
  suppression must not be buildable while ``Settings`` has no such switch.

Tests in ``TestKnownDefects`` are expected to fail against the current implementation. They name
the rule that is not enforced; they are not adjusted to match the code.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

_RANK_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import Settings
from gate_modes import (
    MAX_DROP_POINTS,
    MAX_GRAPH_GAP_POINTS,
    ModeResult,
    evaluate_gate,
)
from modes import (
    FULL_GRAPH,
    GATE_REFERENCE_MODE,
    GATE_SUBJECT_MODE,
    MODES,
    BenchmarkMode,
    UnsupportedModeError,
    modes_with_suppression_support,
    require_supported,
)

_COUNTS = {"dense": 60, "lexical": 50, "graph": 40}
BASELINE = {
    "dense_only": 0.62,
    "hybrid": 0.71,
    "hybrid_rerank": 0.80,
    "full_graph": 0.80,
}


def _result(
    mode: str,
    *,
    overall: float,
    non_graph: float,
    graph: float,
    counts: dict[str, int] | None = None,
    total: int | None = None,
) -> ModeResult:
    per_subset = dict(_COUNTS) if counts is None else counts
    return ModeResult(
        mode=mode,
        overall=overall,
        non_graph=non_graph,
        graph=graph,
        query_count=sum(per_subset.values()) if total is None else total,
        per_subset_counts=per_subset,
    )


def _healthy() -> dict[str, ModeResult]:
    return {
        "dense_only": _result("dense_only", overall=0.62, non_graph=0.60, graph=0.68),
        "hybrid": _result("hybrid", overall=0.71, non_graph=0.70, graph=0.74),
        "hybrid_rerank": _result(
            "hybrid_rerank", overall=0.80, non_graph=0.79, graph=0.83
        ),
        "full_graph": _result("full_graph", overall=0.80, non_graph=0.78, graph=0.86),
    }


def _checks(failures: list) -> list[str]:
    return [failure.check for failure in failures]


class TestCoverageBothDirections:
    def test_a_result_without_a_baseline_fails(self) -> None:
        results = _healthy()
        results["experimental"] = _result(
            "experimental", overall=0.99, non_graph=0.99, graph=0.99
        )

        failures = evaluate_gate(results, BASELINE)

        assert _checks(failures) == ["baseline"]
        assert "experimental" in failures[0].render()

    def test_a_baseline_without_a_result_fails(self) -> None:
        results = _healthy()
        del results["hybrid"]

        failures = evaluate_gate(results, BASELINE)

        assert _checks(failures) == ["coverage"]
        assert "hybrid" in failures[0].render()

    def test_a_run_that_both_drops_and_adds_a_mode_still_fails(self) -> None:
        results = _healthy()
        del results["full_graph"]
        results["experimental"] = _result(
            "experimental", overall=0.99, non_graph=0.99, graph=0.99
        )

        assert "coverage" in _checks(evaluate_gate(results, BASELINE))

    def test_an_extra_mode_is_not_hidden_by_a_headline_pass(self) -> None:
        # overall and non_graph sit above baseline everywhere; only the unbaselined mode fails.
        results = _healthy()
        results["experimental"] = _result(
            "experimental", overall=0.99, non_graph=0.99, graph=0.99
        )

        assert evaluate_gate(results, BASELINE) != []


class TestSubsetSupport:
    def test_subsets_must_account_for_every_query(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid",
            overall=0.71,
            non_graph=0.70,
            graph=0.74,
            counts={"dense": 60, "lexical": 50, "graph": 40},
            total=151,
        )

        assert "subset size" in _checks(evaluate_gate(results, BASELINE))

    def test_an_exact_breakdown_passes(self) -> None:
        assert evaluate_gate(_healthy(), BASELINE) == []

    def test_a_graph_subset_below_the_floor_is_tolerated(self) -> None:
        # Pinned deliberately: the graph subset is excluded from the floor because the gap check
        # never reads the graph score. Reported as an undocumented exemption.
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid",
            overall=0.71,
            non_graph=0.70,
            graph=0.74,
            counts={"dense": 60, "lexical": 50, "graph": 1},
        )

        assert evaluate_gate(results, BASELINE) == []

    def test_scores_at_the_unit_bounds_are_accepted(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=1.0, non_graph=0.0, graph=1.0)

        assert evaluate_gate(results, BASELINE) == []

    def test_a_score_below_zero_fails(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.71, non_graph=-0.01, graph=0.74)

        assert "score range" in _checks(evaluate_gate(results, BASELINE))

    def test_a_nan_score_fails_instead_of_slipping_through(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=float("nan"), non_graph=0.70, graph=0.74
        )

        assert "score range" in _checks(evaluate_gate(results, BASELINE))

    def test_a_graph_score_outside_the_unit_interval_fails(self) -> None:
        # The graph score is published in the report even though no gate check reads it.
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=0.71, non_graph=0.70, graph=1.01
        )

        assert _checks(evaluate_gate(results, BASELINE)) == ["score range"]


class TestBaselineDrop:
    def test_three_points_below_passes(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.68, non_graph=0.67, graph=0.71)

        assert evaluate_gate(results, BASELINE) == []

    def test_a_hair_over_three_points_fails(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=0.6799, non_graph=0.67, graph=0.70
        )

        assert "baseline drop" in _checks(evaluate_gate(results, BASELINE))

    def test_the_allowance_is_not_silently_widened(self) -> None:
        assert MAX_DROP_POINTS == 3.0

    def test_float_noise_at_the_allowance_does_not_fail_the_gate(self) -> None:
        # (0.28 - 0.25) * 100 is 3.0000000000000027: a hair over three points in binary floating
        # point, exactly three points in the policy. The comparison's epsilon exists for this case,
        # and without it a run exactly on the allowance goes red on arithmetic alone.
        results = {
            "hybrid": _result("hybrid", overall=0.25, non_graph=0.25, graph=0.25)
        }

        assert evaluate_gate(results, {"hybrid": 0.28}) == []

    def test_the_slack_band_is_inclusive_at_its_far_edge(self) -> None:
        # (0.25 - 0.21999999999) * 100 is exactly 3.000000001 = MAX_DROP_POINTS + _EPSILON.
        results = {
            "hybrid": _result(
                "hybrid",
                overall=0.21999999999,
                non_graph=0.21999999999,
                graph=0.21999999999,
            )
        }

        assert evaluate_gate(results, {"hybrid": 0.25}) == []

    def test_a_drop_past_the_slack_band_fails(self) -> None:
        # One nanometre past the band: (0.25 - 0.2199999999) * 100 is 3.00000001.
        results = {
            "hybrid": _result(
                "hybrid",
                overall=0.2199999999,
                non_graph=0.2199999999,
                graph=0.2199999999,
            )
        }

        failures = evaluate_gate(results, {"hybrid": 0.25})

        assert _checks(failures) == ["baseline drop"]

    def test_a_mode_above_its_baseline_is_never_punished(self) -> None:
        results = _healthy()
        results["hybrid"] = _result("hybrid", overall=0.95, non_graph=0.95, graph=0.95)

        assert evaluate_gate(results, BASELINE) == []


class TestGraphGapBoundaries:
    @pytest.mark.parametrize(
        ("subject_non_graph", "should_fail"),
        [
            (0.78, False),  # gap 1.00
            (0.7700001, False),  # gap 1.9999999
            (0.7699, True),  # gap 2.01
            (0.60, True),  # gap 19.0
        ],
    )
    def test_gap_is_measured_in_absolute_points(
        self, subject_non_graph: float, should_fail: bool
    ) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "full_graph", overall=0.80, non_graph=subject_non_graph, graph=0.86
        )

        assert ("graph gap" in _checks(evaluate_gate(results, BASELINE))) is should_fail

    def test_exactly_two_points_is_inside_the_allowance(self) -> None:
        results = _healthy()
        # 0.79 - 0.77 is not exactly 0.02 in binary floating point; the allowance is inclusive.
        results["full_graph"] = _result(
            "full_graph", overall=0.80, non_graph=0.77, graph=0.86
        )

        assert evaluate_gate(results, BASELINE) == []

    def test_the_allowance_is_not_silently_widened(self) -> None:
        assert MAX_GRAPH_GAP_POINTS == 2.0

    def test_a_better_overall_score_does_not_excuse_a_non_graph_regression(
        self,
    ) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "full_graph", overall=0.95, non_graph=0.60, graph=0.99
        )

        failures = evaluate_gate(results, BASELINE)

        assert _checks(failures) == ["graph gap"]

    def test_a_better_non_graph_score_does_not_offset_a_baseline_drop(self) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "full_graph", overall=0.70, non_graph=0.85, graph=0.50
        )

        failures = evaluate_gate(results, BASELINE)

        assert _checks(failures) == ["baseline drop"]

    def test_the_gap_ignores_the_graph_score(self) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "full_graph", overall=0.80, non_graph=0.79, graph=0.10
        )

        assert evaluate_gate(results, BASELINE) == []

    def test_a_subject_ahead_of_the_reference_is_never_punished(self) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "full_graph", overall=0.80, non_graph=0.85, graph=0.86
        )

        assert evaluate_gate(results, BASELINE) == []

    def test_the_missing_reference_is_caught_by_coverage_when_baselined(self) -> None:
        results = _healthy()
        del results["hybrid_rerank"]

        failures = evaluate_gate(results, BASELINE)

        assert _checks(failures) == ["coverage"]
        assert "hybrid_rerank" in failures[0].render()

    def test_gate_defaults_agree_with_the_published_pair(self) -> None:
        params = inspect.signature(evaluate_gate).parameters

        assert (
            params["reference_mode"].default == GATE_REFERENCE_MODE == "hybrid_rerank"
        )
        assert params["subject_mode"].default == GATE_SUBJECT_MODE == "full_graph"


class TestModeIdentity:
    def test_a_result_whose_declared_mode_differs_from_its_key_fails(self) -> None:
        results = _healthy()
        results["full_graph"] = _result(
            "hybrid_rerank", overall=0.80, non_graph=0.78, graph=0.86
        )

        failures = evaluate_gate(results, BASELINE)

        assert failures != []
        assert "full_graph" in failures[0].render()


class TestModeDeltas:
    def test_a_mode_changes_only_the_fields_its_delta_names(self) -> None:
        base = Settings(composite_relevance_floor=0.2, search_rrf_k=42)

        for mode in MODES:
            settings = mode.settings_for(base)
            for field in Settings.model_fields:
                if field in mode.settings_delta:
                    continue
                assert getattr(settings, field) == getattr(base, field), (
                    f"{mode.name} changed {field} outside its delta"
                )

    def test_a_mode_does_not_mutate_the_base_settings(self) -> None:
        base = Settings()
        before = dict(base.__dict__)

        for mode in MODES:
            mode.settings_for(base)

        assert base.__dict__ == before
        assert not hasattr(base, "conflict_suppression_enabled")

    def test_every_delta_key_is_a_real_setting_except_the_documented_switch(
        self,
    ) -> None:
        for mode in MODES:
            unknown = set(mode.settings_delta) - set(Settings.model_fields)
            if mode.conflict_suppression:
                assert unknown == {"conflict_suppression_enabled"}
            else:
                assert unknown == set(), (
                    f"{mode.name} sets a field Settings does not define"
                )

    def test_a_suppression_mode_whose_delta_does_not_enable_it_is_refused(self) -> None:
        lied = BenchmarkMode(
            name="declares_suppression",
            description="declares conflict suppression but never turns it on",
            hybrid=True,
            rerank=True,
            conflict_suppression=True,
            settings_delta=MappingProxyType({"search_hybrid_enabled": True}),
        )

        with pytest.raises(UnsupportedModeError, match="conflict suppression"):
            lied.settings_for(Settings())

    def test_require_supported_refuses_a_declared_switch_the_service_lacks(
        self,
    ) -> None:
        with pytest.raises(UnsupportedModeError, match="conflict_suppression_enabled"):
            require_supported(FULL_GRAPH, Settings())

    def test_require_supported_rejects_a_self_contradicting_mode(self) -> None:
        # Declaring suppression while the delta disables it must be refused even when the base
        # happens to carry the field: require_supported has to apply the mode, not just look at it.
        lied = BenchmarkMode(
            name="declares_suppression_disabled",
            description="declares conflict suppression but turns it off",
            hybrid=True,
            rerank=True,
            conflict_suppression=True,
            settings_delta=MappingProxyType({"conflict_suppression_enabled": False}),
        )
        base = Settings().model_copy(update={"conflict_suppression_enabled": True})

        with pytest.raises(UnsupportedModeError, match="conflict suppression"):
            require_supported(lied, base)

    def test_the_runnable_list_agrees_with_require_supported(self) -> None:
        bases = [
            Settings(),
            Settings().model_copy(update={"conflict_suppression_enabled": True}),
            FULL_GRAPH.settings_for(Settings()),
        ]

        for base in bases:
            expected = []
            for mode in MODES:
                try:
                    require_supported(mode, base)
                except UnsupportedModeError:
                    continue
                expected.append(mode.name)
            assert [
                mode.name for mode in modes_with_suppression_support(base)
            ] == expected

    def test_the_runnable_list_keeps_publication_order(self) -> None:
        names = [mode.name for mode in modes_with_suppression_support(Settings())]

        assert names == ["dense_only", "hybrid", "hybrid_rerank"]


class TestKnownDefects:
    """Rules the implementation states but does not enforce. These fail on purpose."""

    def test_score_for_returns_the_score_not_the_field_name(self) -> None:
        result = _healthy()["hybrid"]

        assert result.score_for("overall") == pytest.approx(0.71)
        assert result.score_for("non_graph") == pytest.approx(0.70)
        assert result.score_for("graph") == pytest.approx(0.74)

    def test_an_empty_subset_breakdown_cannot_account_for_the_corpus(self) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid", overall=0.71, non_graph=0.70, graph=0.74, counts={}, total=500
        )

        assert "subset size" in _checks(evaluate_gate(results, BASELINE))

    def test_a_published_score_needs_support_in_its_own_subset(self) -> None:
        # No non_graph queries were evaluated, yet the graph-gap check compares the non_graph
        # mean of both modes. 150 queries of "dense" only must not count as support.
        results = _healthy()
        results["hybrid_rerank"] = _result(
            "hybrid_rerank",
            overall=0.80,
            non_graph=0.79,
            graph=0.83,
            counts={"dense": 150},
        )
        results["full_graph"] = _result(
            "full_graph",
            overall=0.80,
            non_graph=0.78,
            graph=0.86,
            counts={"dense": 150},
        )

        assert evaluate_gate(results, BASELINE) != []

    def test_a_subset_that_is_not_a_corpus_subset_does_not_count_as_support(
        self,
    ) -> None:
        results = _healthy()
        results["hybrid"] = _result(
            "hybrid",
            overall=0.71,
            non_graph=0.70,
            graph=0.74,
            counts={"dense": 60, "lexical": 50, "graph": 40, "typo_subset": 30},
        )

        assert evaluate_gate(results, BASELINE) != []

    def test_a_nan_baseline_cannot_disable_the_drop_check(self) -> None:
        results = _healthy()

        failures = evaluate_gate(results, {**BASELINE, "hybrid": float("nan")})

        assert failures != []

    def test_a_gate_that_never_compared_the_pair_does_not_pass(self) -> None:
        # A baseline that predates the graph modes, or a typo in reference_mode, must not turn the
        # milestone's only relative check into a silent no-op.
        results = {name: _healthy()[name] for name in ("dense_only", "hybrid")}
        baseline = {"dense_only": 0.62, "hybrid": 0.71}

        assert evaluate_gate(results, baseline) != []
        assert evaluate_gate(_healthy(), BASELINE, reference_mode="hybrid-rerank") != []

    def test_an_injected_attribute_does_not_make_the_service_support_the_switch(
        self,
    ) -> None:
        # Settings() has no conflict_suppression_enabled field; model_copy(update=...) injects an
        # instance attribute that hasattr() cannot distinguish from a real switch.
        base = Settings().model_copy(update={"conflict_suppression_enabled": True})

        assert "conflict_suppression_enabled" not in Settings.model_fields
        with pytest.raises(UnsupportedModeError):
            require_supported(FULL_GRAPH, base)

    def test_the_mode_output_cannot_be_its_own_permission_slip(self) -> None:
        # settings_for injects the attribute, so chaining it into require_supported must not
        # convince the guard that the service grew the switch.
        built = FULL_GRAPH.settings_for(Settings())

        with pytest.raises(UnsupportedModeError):
            require_supported(FULL_GRAPH, built)
