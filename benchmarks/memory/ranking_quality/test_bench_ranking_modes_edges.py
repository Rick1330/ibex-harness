"""Adversarial tests for the multi-mode scoring: boundaries, malformed input, published artifact.

These complement ``test_bench_ranking_modes.py``. Each test names one behaviour, and each one
fails for a plausible mutation of the scorer rather than for a refactor of it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

_RANK_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import bench_ranking_modes as bench
from gate_modes import ModeResult, evaluate_gate


def _score(outcomes: list[Any]) -> ModeResult:
    return bench.score_mode(outcomes)


def _outcome(query_id: str, subset: str, ranked: list[str], expected: list[str]) -> Any:
    return bench.QueryOutcome(
        query_id=query_id, subset=subset, ranked_ids=ranked, expected_ids=expected
    )


def _hits(subset: str, count: int) -> list[bench.QueryOutcome]:
    """``count`` perfect answers in one subset."""
    return [
        _outcome(f"{subset}-{index}", subset, [f"{subset}{index}"], [f"{subset}{index}"])
        for index in range(count)
    ]


def _subset_failures(failures: list[Any], mode: str, needle: str) -> list[Any]:
    return [
        failure
        for failure in failures
        if failure.mode == mode and failure.check == "subset size" and needle in failure.detail
    ]


class TestScoringArithmetic:
    def test_a_repeated_id_in_a_page_is_rejected_rather_than_credited_twice(self) -> None:
        with pytest.raises(ValueError, match="duplicate ids"):
            bench.score_mode([_outcome("q1", "dense", ["a", "a"], ["a"])])

    def test_duplicate_expected_ids_do_not_inflate_the_score(self) -> None:
        duplicated = bench.score_mode([_outcome("q1", "dense", ["a"], ["a", "a"])])

        assert duplicated.overall == pytest.approx(1.0)

    def test_a_page_shorter_than_the_expected_set_is_not_a_perfect_score(self) -> None:
        # Expected a and b, returned only a: DCG 1/log2(2) over ideal 1/log2(2) + 1/log2(3).
        result = bench.score_mode([_outcome("q1", "dense", ["a"], ["a", "b"])])

        assert result.overall == pytest.approx(1.0 / (1.0 + 1.0 / math.log2(3)), rel=1e-12)

    def test_an_empty_page_with_expected_documents_scores_zero(self) -> None:
        result = bench.score_mode([_outcome("q1", "dense", [], ["a"])])

        assert result.overall == 0.0

    def test_documents_outside_the_expected_set_earn_no_credit(self) -> None:
        result = bench.score_mode([_outcome("q1", "dense", ["x", "y", "z"], ["a"])])

        assert result.overall == 0.0

    def test_the_tenth_ranked_document_is_still_counted(self) -> None:
        # Nine misses then the answer at position 10: gain 1 discounted by log2(11).
        ranked = [f"noise{index}" for index in range(bench.TOP_K - 1)] + ["a"]
        result = bench.score_mode([_outcome("q1", "dense", ranked, ["a"])])

        assert result.overall == pytest.approx(1.0 / math.log2(11), rel=1e-12)

    def test_a_perfect_page_is_one_even_when_more_documents_are_relevant(self) -> None:
        expected = [f"e{index}" for index in range(bench.TOP_K + 1)]
        result = bench.score_mode([_outcome("q1", "dense", expected[: bench.TOP_K], expected)])

        assert result.overall == pytest.approx(1.0)

    def test_a_query_with_no_expected_ids_is_rejected_not_scored_zero(self) -> None:
        # An unresolved gold key looks like a total miss; scoring it 0.0 would drag the
        # published number down with no diagnostic.
        with pytest.raises(ValueError, match="no expected ids"):
            _score([_outcome("q1", "dense", ["a"], [])])

    def test_a_repeated_query_row_is_rejected(self) -> None:
        # Weighting one query twice leaves query_count and the subset counts consistent, so
        # nothing downstream could notice.
        with pytest.raises(ValueError, match="duplicate query_id"):
            _score([_outcome("q1", "graph", ["a"], ["a"]), _outcome("q1", "graph", ["a"], ["a"])])

    def test_duplicate_expected_ids_do_not_double_count_a_query(self) -> None:
        result = _score([_outcome("q1", "dense", ["a", "b"], ["a", "a", "b"])])

        assert result.overall == pytest.approx(1.0)


class TestSubsetAggregation:
    def test_non_graph_pools_the_queries_of_both_subsets(self) -> None:
        outcomes = [*_hits("dense", 3), _outcome("lexical-0", "lexical", ["x"], ["y"])]

        result = bench.score_mode(outcomes)

        # Three of four non-graph queries were answered, so the pooled mean is 0.75; averaging
        # the two subset means would report 0.5 and hide the lexical failure.
        assert result.non_graph == pytest.approx(0.75)

    def test_overall_pools_every_query_not_every_subset(self) -> None:
        outcomes = [*_hits("dense", 3), _outcome("lexical-0", "lexical", ["x"], ["y"])]

        assert bench.score_mode(outcomes).overall == pytest.approx(0.75)

    def test_the_graph_subset_never_counts_towards_non_graph(self) -> None:
        outcomes = [*_hits("dense", 1), *_hits("lexical", 1), _outcome("g", "graph", ["x"], ["y"])]

        result = bench.score_mode(outcomes)

        assert result.non_graph == pytest.approx(1.0)
        assert result.graph == pytest.approx(0.0)

    def test_an_unmeasured_subset_is_reported_as_zero_rather_than_omitted(self) -> None:
        outcomes = [*_hits("dense", 2), *_hits("graph", 1)]

        counts = bench.score_mode(outcomes).per_subset_counts

        assert counts == {"dense": 2, "lexical": 0, "graph": 1}

    def test_the_derived_non_graph_name_is_not_an_accepted_input_subset(self) -> None:
        with pytest.raises(ValueError, match="unknown subset"):
            bench.score_mode([_outcome("q1", "non_graph", ["a"], ["a"])])

    def test_the_gate_rejects_a_run_that_measured_no_lexical_queries(self) -> None:
        result = bench.with_mode(bench.score_mode([*_hits("dense", 10), *_hits("graph", 10)]), "m")

        failures = evaluate_gate({"m": result}, {"m": 1.0})

        assert _subset_failures(failures, "m", "lexical"), failures

    def test_the_gate_rejects_a_mode_with_no_outcomes_at_all(self) -> None:
        result = bench.with_mode(bench.score_mode([]), "m")

        failures = evaluate_gate({"m": result}, {"m": 1.0})

        assert any(failure.check == "corpus size" for failure in failures), failures


class TestPayload:
    def _result(self, *, overall: float, non_graph: float, graph: float) -> ModeResult:
        return ModeResult(
            mode="m",
            overall=overall,
            non_graph=non_graph,
            graph=graph,
            query_count=30,
            per_subset_counts={"dense": 10, "lexical": 10, "graph": 10},
        )

    def test_rounding_keeps_published_scores_inside_the_unit_interval(self) -> None:
        for value in (0.0, 4e-7, 0.5, 1.0 - 1e-10, 1.0):
            payload = bench.build_payload(
                {"m": self._result(overall=value, non_graph=value, graph=value)},
                gold_set="g",
                reranker="r",
            )
            published = payload["modes"]["m"]

            for key in ("ndcg_at_10", "non_graph_ndcg_at_10", "graph_ndcg_at_10"):
                assert 0.0 <= published[key] <= 1.0, (value, key, published[key])

    def test_a_score_one_unit_below_rounding_does_not_round_above_one(self) -> None:
        payload = bench.build_payload(
            {"m": self._result(overall=1.0 - 1e-10, non_graph=1.0 - 1e-10, graph=1.0 - 1e-10)},
            gold_set="g",
            reranker="r",
        )

        assert payload["modes"]["m"]["ndcg_at_10"] == 1.0

    def test_every_published_score_is_rounded_to_six_decimal_places(self) -> None:
        payload = bench.build_payload(
            {"m": self._result(overall=1 / 3, non_graph=1 / 3, graph=2 / 3)},
            gold_set="g",
            reranker="r",
        )

        published = payload["modes"]["m"]
        assert published["ndcg_at_10"] == 0.333333
        assert published["non_graph_ndcg_at_10"] == 0.333333
        assert published["graph_ndcg_at_10"] == 0.666667

    def test_the_payload_key_names_are_exact(self) -> None:
        payload = bench.build_payload(
            {"m": self._result(overall=0.5, non_graph=0.5, graph=0.5)},
            gold_set="g",
            reranker="r",
        )

        assert list(payload) == [
            "schema_version",
            "benchmark",
            "gold_set",
            "top_k",
            "reranker",
            "modes",
        ]
        assert list(payload["modes"]["m"]) == [
            "ndcg_at_10",
            "non_graph_ndcg_at_10",
            "graph_ndcg_at_10",
            "query_count",
            "per_subset_counts",
        ]

    def test_modes_are_published_in_sorted_order_whatever_the_caller_order(self) -> None:
        result = self._result(overall=0.5, non_graph=0.5, graph=0.5)

        payload = bench.build_payload(
            {"zeta": result, "alpha": result, "mid": result}, gold_set="g", reranker="r"
        )

        assert list(payload["modes"]) == ["alpha", "mid", "zeta"]


class TestMain:
    def _outcomes_file(self, tmp_path: Path, document: Any) -> Path:
        path = tmp_path / "outcomes.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_a_mode_with_no_outcomes_is_written_honestly_as_zero(self, tmp_path: Path, monkeypatch: Any) -> None:
        output = tmp_path / "out"
        monkeypatch.setattr(bench, "OUTPUT_DIR", output)
        outcomes = self._outcomes_file(
            tmp_path,
            {"modes": {"empty": [], "measured": [
                {"query_id": "q", "subset": "dense", "ranked_ids": ["a"], "expected_ids": ["a"]}
            ]}},
        )

        assert bench.main(["bench", "--outcomes", str(outcomes)]) == 0

        published = json.loads((output / "modes-latest.json").read_text(encoding="utf-8"))
        empty = published["modes"]["empty"]
        assert empty["query_count"] == 0
        assert empty["per_subset_counts"] == {"dense": 0, "lexical": 0, "graph": 0}
        assert empty["ndcg_at_10"] == 0.0

    def test_a_malformed_outcome_fails_loudly_and_leaves_the_artifact_alone(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        output = tmp_path / "out"
        output.mkdir()
        artifact = output / "modes-latest.json"
        artifact.write_text('{"previous": true}\n', encoding="utf-8")
        monkeypatch.setattr(bench, "OUTPUT_DIR", output)
        outcomes = self._outcomes_file(
            tmp_path,
            {"modes": {"m": [{"query_id": "q", "subset": "dense", "ranked_ids": ["a"]}]}},
        )

        with pytest.raises(KeyError):
            bench.main(["bench", "--outcomes", str(outcomes)])

        assert artifact.read_text(encoding="utf-8") == '{"previous": true}\n'

    def test_a_repeated_ranked_id_in_the_recorded_file_aborts_the_run(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        output = tmp_path / "out"
        monkeypatch.setattr(bench, "OUTPUT_DIR", output)
        outcomes = self._outcomes_file(
            tmp_path,
            {"modes": {"m": [
                {"query_id": "q", "subset": "dense", "ranked_ids": ["a", "a"], "expected_ids": ["a"]}
            ]}},
        )

        with pytest.raises(ValueError, match="duplicate ids"):
            bench.main(["bench", "--outcomes", str(outcomes)])

        assert not (output / "modes-latest.json").exists()

    def test_the_written_artifact_is_strict_json(self, tmp_path: Path, monkeypatch: Any) -> None:
        def _reject(token: str) -> None:
            raise AssertionError(f"non-finite number published as {token}")

        output = tmp_path / "out"
        monkeypatch.setattr(bench, "OUTPUT_DIR", output)
        outcomes = self._outcomes_file(
            tmp_path,
            {"modes": {"none": [], "measured": [
                {"query_id": "q", "subset": "dense", "ranked_ids": ["a"], "expected_ids": ["a"]}
            ]}},
        )

        bench.main(["bench", "--outcomes", str(outcomes)])

        json.loads((output / "modes-latest.json").read_text(encoding="utf-8"), parse_constant=_reject)

    def test_the_artifact_is_written_inside_the_benchmark_directory(self, tmp_path: Path, monkeypatch: Any) -> None:
        assert bench.OUTPUT_DIR.parent == Path(bench.__file__).resolve().parent
        assert bench.OUTPUT_DIR.name == "output"

        output = tmp_path / "out"
        monkeypatch.setattr(bench, "OUTPUT_DIR", output)
        outcomes = self._outcomes_file(
            tmp_path,
            {"modes": {"m": [
                {"query_id": "q", "subset": "dense", "ranked_ids": ["a"], "expected_ids": ["a"]}
            ]}},
        )

        bench.main(["bench", "--outcomes", str(outcomes)])

        assert sorted(entry.name for entry in output.iterdir()) == ["modes-latest.json"]
