"""Tests for the multi-mode scoring: pure arithmetic, no database."""

from __future__ import annotations

import json
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
from gate_modes import evaluate_gate


def _outcome(query_id: str, subset: str, ranked: list[str], expected: list[str]) -> Any:
    return bench.QueryOutcome(
        query_id=query_id, subset=subset, ranked_ids=ranked, expected_ids=expected
    )


def _perfect_outcomes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for subset in ("dense", "lexical", "graph"):
        for index in range(10):
            key = f"{subset}-{index}"
            rows.append(
                {
                    "query_id": f"q_{key}",
                    "subset": subset,
                    "ranked_ids": [key],
                    "expected_ids": [key],
                }
            )
    return rows


def _perfect_run(modes: list[str]) -> dict[str, Any]:
    return {"modes": {mode: _perfect_outcomes() for mode in modes}}


class TestScoring:
    def test_a_perfect_page_scores_one(self) -> None:
        result = bench.score_mode([_outcome("q1", "dense", ["a", "x"], ["a"])])

        assert result.overall == pytest.approx(1.0)

    def test_the_answer_at_the_wrong_rank_is_discounted(self) -> None:
        result = bench.score_mode([_outcome("q1", "dense", ["x", "a"], ["a"])])

        assert 0.0 < result.overall < 1.0

    def test_a_missing_answer_scores_zero(self) -> None:
        result = bench.score_mode([_outcome("q1", "dense", ["x"], ["a"])])

        assert result.overall == 0.0

    def test_only_the_top_ten_count(self) -> None:
        ranked = [f"noise{i}" for i in range(bench.TOP_K)] + ["a"]
        result = bench.score_mode([_outcome("q1", "dense", ranked, ["a"])])

        assert result.overall == 0.0

    def test_graph_and_non_graph_are_averaged_separately(self) -> None:
        outcomes = [
            _outcome("q1", "dense", ["a"], ["a"]),
            _outcome("q2", "lexical", ["b"], ["b"]),
            _outcome("q3", "graph", ["x"], ["c"]),
        ]

        result = bench.score_mode(outcomes)

        assert result.non_graph == pytest.approx(1.0)
        assert result.graph == pytest.approx(0.0)
        assert result.overall == pytest.approx(2 / 3)

    def test_per_subset_counts_are_reportable(self) -> None:
        outcomes = [
            _outcome("q1", "dense", ["a"], ["a"]),
            _outcome("q2", "dense", ["b"], ["b"]),
            _outcome("q3", "graph", ["c"], ["c"]),
        ]

        counts = bench.score_mode(outcomes).per_subset_counts

        assert counts == {"dense": 2, "lexical": 0, "graph": 1}

    def test_an_unknown_subset_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown subset"):
            bench.score_mode([_outcome("q1", "vibes", ["a"], ["a"])])

    def test_an_empty_run_scores_zero_rather_than_dividing_by_zero(self) -> None:
        result = bench.score_mode([])

        assert result.overall == 0.0
        assert result.query_count == 0


class TestPayload:
    def test_the_payload_names_the_definitions(self) -> None:
        payload = bench.build_payload(
            {"hybrid": bench.with_mode(bench.score_mode([_outcome("q1", "dense", ["a"], ["a"])]), "hybrid")},
            gold_set="ranking_quality_v2",
            reranker="stub/lexical-overlap@1",
        )

        assert payload["schema_version"] == 2
        assert payload["top_k"] == bench.TOP_K
        assert payload["reranker"] == "stub/lexical-overlap@1"

    def test_scores_are_rounded_to_published_precision(self) -> None:
        payload = bench.build_payload(
            {"hybrid": bench.with_mode(bench.score_mode([_outcome("q1", "dense", ["x", "a"], ["a"])]), "hybrid")},
            gold_set="g",
            reranker="r",
        )

        value = payload["modes"]["hybrid"]["ndcg_at_10"]
        assert round(value, 6) == value


class TestEndToEnd:
    def test_recorded_outcomes_produce_an_artifact_that_gates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "output")
        outcomes = tmp_path / "outcomes.json"
        outcomes.write_text(json.dumps(_perfect_run(["dense_only", "hybrid", "hybrid_rerank", "full_graph"])))

        assert bench.main(["bench", "--outcomes", str(outcomes)]) == 0

        payload = json.loads((bench.OUTPUT_DIR / "modes-latest.json").read_text())
        results = {
            name: bench.with_mode(
                bench.score_mode(
                    bench.QueryOutcome(
                        query_id=o["query_id"],
                        subset=o["subset"],
                        ranked_ids=o["ranked_ids"],
                        expected_ids=o["expected_ids"],
                    )
                    for o in _perfect_outcomes()
                ),
                name,
            )
            for name in payload["modes"]
        }
        baseline = {name: 1.0 for name in results}

        assert evaluate_gate(results, baseline) == []
