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
    return {
        "reranker": "stub/lexical-overlap@1",
        "gold_set": "ranking_quality_v2",
        "modes": {mode: _perfect_outcomes() for mode in modes},
    }


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
        outcome = _outcome("q1", "vibes", ["a"], ["a"])

        with pytest.raises(ValueError, match="unknown subset"):
            bench.score_mode([outcome])

    def test_an_empty_run_scores_zero_rather_than_dividing_by_zero(self) -> None:
        result = bench.score_mode([])

        assert result.overall == 0.0
        assert result.query_count == 0


class TestPayload:
    def test_the_payload_names_the_definitions(self) -> None:
        payload = bench.build_payload(
            {
                "hybrid": bench.with_mode(
                    bench.score_mode([_outcome("q1", "dense", ["a"], ["a"])]), "hybrid"
                )
            },
            gold_set="ranking_quality_v2",
            reranker="stub/lexical-overlap@1",
        )

        assert payload["schema_version"] == 2
        assert payload["top_k"] == bench.TOP_K
        assert payload["reranker"] == "stub/lexical-overlap@1"

    def test_scores_are_rounded_to_published_precision(self) -> None:
        payload = bench.build_payload(
            {
                "hybrid": bench.with_mode(
                    bench.score_mode([_outcome("q1", "dense", ["x", "a"], ["a"])]),
                    "hybrid",
                )
            },
            gold_set="g",
            reranker="r",
        )

        value = payload["modes"]["hybrid"]["ndcg_at_10"]
        assert round(value, 6) == value


class TestEndToEnd:
    def test_recorded_outcomes_produce_an_artifact_that_gates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "output")
        outcomes = tmp_path / "outcomes.json"
        outcomes.write_text(
            json.dumps(
                _perfect_run(["dense_only", "hybrid", "hybrid_rerank", "full_graph"])
            )
        )

        assert bench.main(["bench", "--outcomes", str(outcomes)]) == 0

        payload = json.loads((bench.OUTPUT_DIR / "modes-latest.json").read_text())
        results = results_from_payload(payload)

        # The gate is fed the numbers the artifact *saved*, not numbers recomputed from the
        # fixtures: a wrong score or count written by main() has to fail here.
        for result in results.values():
            assert result.overall == pytest.approx(1.0)
            assert result.query_count == 30
            assert result.per_subset_counts == {"dense": 10, "lexical": 10, "graph": 10}
        assert evaluate_gate(results, {name: 1.0 for name in results}) == []

    def test_a_mode_that_ranked_worse_fails_the_gate_on_its_saved_score(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "output")
        recorded = _perfect_run(["dense_only", "hybrid", "hybrid_rerank", "full_graph"])
        # One mode answers at rank 2 instead of rank 1 — a real regression, expressed only as
        # a worse ranking, never as a precomputed score.
        for row in recorded["modes"]["full_graph"]:
            row["ranked_ids"] = [f"noise-{row['query_id']}", *row["ranked_ids"]]
        outcomes = tmp_path / "outcomes.json"
        outcomes.write_text(json.dumps(recorded))

        assert bench.main(["bench", "--outcomes", str(outcomes)]) == 0

        payload = json.loads((bench.OUTPUT_DIR / "modes-latest.json").read_text())
        results = results_from_payload(payload)
        baseline = {name: 1.0 for name in results}

        assert results["full_graph"].overall < 1.0
        assert evaluate_gate(results, baseline) != []

    def test_corrupting_the_saved_score_flips_the_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the gate reads the artifact: the same run passes until the number is wrong."""
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "output")
        outcomes = tmp_path / "outcomes.json"
        outcomes.write_text(json.dumps(_perfect_run(["hybrid_rerank", "full_graph"])))
        assert bench.main(["bench", "--outcomes", str(outcomes)]) == 0

        payload = json.loads((bench.OUTPUT_DIR / "modes-latest.json").read_text())
        baseline = {name: 1.0 for name in payload["modes"]}
        assert evaluate_gate(results_from_payload(payload), baseline) == []

        payload["modes"]["full_graph"]["ndcg_at_10"] = 0.5
        assert evaluate_gate(results_from_payload(payload), baseline) != []


def results_from_payload(payload: dict[str, Any]) -> dict[str, bench.ModeResult]:
    """Rebuild the gate's input from the artifact's own fields.

    Deliberately not a rescoring call: a test that recomputes the expected value from the same
    fixture the production code read cannot detect a wrong number in the artifact.
    """
    return {
        name: bench.ModeResult(
            mode=name,
            overall=body["ndcg_at_10"],
            non_graph=body["non_graph_ndcg_at_10"],
            graph=body["graph_ndcg_at_10"],
            query_count=body["query_count"],
            per_subset_counts=body["per_subset_counts"],
        )
        for name, body in payload["modes"].items()
    }


class TestRecordedRun:
    """The gate compares modes, so the modes must be comparable before anything is scored."""

    def _write(self, tmp_path: Path, modes: dict[str, Any]) -> Path:
        target = tmp_path / "outcomes.json"
        target.write_text(
            json.dumps({"reranker": "stub/lexical-overlap@1", "modes": modes})
        )
        return target

    def test_a_mode_that_dropped_a_hard_query_is_rejected(self, tmp_path: Path) -> None:
        # Without this, the mode that quietly dropped a query it could not answer reports a
        # better mean and still clears the per-subset minimum-count check.
        complete = _perfect_outcomes()
        thinned = [row for row in complete if row["query_id"] != "q_graph-3"]
        target = self._write(tmp_path, {"hybrid": complete, "full_graph": thinned})

        with pytest.raises(ValueError, match="not comparable"):
            bench.load_recorded(target)

    def test_the_error_names_the_mode_and_the_missing_query(
        self, tmp_path: Path
    ) -> None:
        complete = _perfect_outcomes()
        thinned = [row for row in complete if row["query_id"] != "q_graph-3"]
        target = self._write(tmp_path, {"hybrid": complete, "full_graph": thinned})

        with pytest.raises(ValueError, match="full_graph.*missing 1"):
            bench.load_recorded(target)

    def test_a_mode_that_scored_extra_queries_is_rejected(self, tmp_path: Path) -> None:
        complete = _perfect_outcomes()
        extra = {
            "query_id": "q_extra",
            "subset": "dense",
            "ranked_ids": ["a"],
            "expected_ids": ["a"],
        }
        target = self._write(
            tmp_path, {"hybrid": complete, "full_graph": [*complete, extra]}
        )

        with pytest.raises(ValueError, match="the baseline did not"):
            bench.load_recorded(target)

    def test_a_mode_that_changed_the_expectations_is_rejected(
        self, tmp_path: Path
    ) -> None:
        complete = _perfect_outcomes()
        tampered = [dict(row) for row in complete]
        tampered[0]["expected_ids"] = ["something-else"]
        target = self._write(tmp_path, {"hybrid": complete, "full_graph": tampered})

        with pytest.raises(ValueError, match="differ in subset or expectations"):
            bench.load_recorded(target)

    def test_a_mode_that_changed_the_subset_is_rejected(self, tmp_path: Path) -> None:
        # Re-labelling a failed graph query as dense would move it out of the subset the gate
        # compares, which is the same cheat as dropping it.
        complete = _perfect_outcomes()
        tampered = [dict(row) for row in complete]
        tampered[0]["subset"] = "dense" if tampered[0]["subset"] != "dense" else "graph"
        target = self._write(tmp_path, {"hybrid": complete, "full_graph": tampered})

        with pytest.raises(ValueError, match="differ in subset or expectations"):
            bench.load_recorded(target)

    def test_row_order_may_differ_between_modes(self, tmp_path: Path) -> None:
        complete = _perfect_outcomes()
        target = self._write(
            tmp_path, {"hybrid": complete, "full_graph": list(reversed(complete))}
        )

        loaded = bench.load_recorded(target)

        assert set(loaded.modes) == {"hybrid", "full_graph"}

    def test_expected_id_order_may_differ_between_modes(self, tmp_path: Path) -> None:
        complete = _perfect_outcomes()
        for row in complete:
            row["expected_ids"] = [*row["expected_ids"], "second-relevant"]
        reordered = [dict(row) for row in complete]
        for row in reordered:
            row["expected_ids"] = list(reversed(row["expected_ids"]))
        target = self._write(tmp_path, {"hybrid": complete, "full_graph": reordered})

        bench.load_recorded(target)

    def test_a_row_missing_a_key_names_the_key_and_row(self, tmp_path: Path) -> None:
        broken = _perfect_outcomes()
        del broken[4]["ranked_ids"]
        target = self._write(tmp_path, {"hybrid": broken})

        with pytest.raises(ValueError, match=r"hybrid.*row 4.*'ranked_ids'"):
            bench.load_recorded(target)

    def test_an_outcomes_file_with_no_modes_is_rejected(self, tmp_path: Path) -> None:
        target = self._write(tmp_path, {})

        with pytest.raises(ValueError, match="no modes to score"):
            bench.load_recorded(target)

    def test_the_end_to_end_path_refuses_an_incomparable_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "output")
        complete = _perfect_outcomes()
        outcomes = self._write(
            tmp_path, {"hybrid": complete, "full_graph": complete[:-1]}
        )

        with pytest.raises(ValueError, match="not comparable"):
            bench.main(["bench", "--outcomes", str(outcomes)])
        assert not (tmp_path / "output" / "modes-latest.json").exists()


class TestMalformedRecords:
    def test_a_row_that_is_not_an_object_names_the_mode_and_row(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "outcomes.json"
        target.write_text(json.dumps({"modes": {"hybrid": ["not-a-row"]}}))

        with pytest.raises(ValueError, match=r"hybrid.*row 0 is not an object"):
            bench.load_recorded(target)

    def test_modes_that_are_not_a_mapping_are_rejected(self, tmp_path: Path) -> None:
        target = tmp_path / "outcomes.json"
        target.write_text(json.dumps({"modes": ["hybrid"]}))

        with pytest.raises(ValueError, match="no modes to score"):
            bench.load_recorded(target)


class TestInputConfinement:
    """A CLI path is confined to the benchmark directory, not trusted because it is a CLI path."""

    def test_a_recorded_run_outside_the_benchmark_directory_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from path_guard import UnsafePathError

        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps({"modes": {"m": []}}))
        root = tmp_path / "bench"
        root.mkdir()
        monkeypatch.setattr(bench, "INPUT_ROOT", root)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")

        with pytest.raises(UnsafePathError, match="escapes"):
            bench.main(["bench", "--outcomes", str(outside)])
        assert not (tmp_path / "out" / "modes-latest.json").exists()

    def test_a_parent_reference_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from path_guard import UnsafePathError

        root = tmp_path / "bench"
        root.mkdir()
        (tmp_path / "sibling.json").write_text(json.dumps({"modes": {"m": []}}))
        monkeypatch.setattr(bench, "INPUT_ROOT", root)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")

        with pytest.raises(UnsafePathError, match="parent references"):
            bench.main(["bench", "--outcomes", "../sibling.json"])

    def test_a_missing_recorded_run_is_refused_by_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from path_guard import UnsafePathError

        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")

        with pytest.raises(UnsafePathError, match="file not found"):
            bench.main(["bench", "--outcomes", str(tmp_path / "absent.json")])


class TestStrictRecording:
    """Every rejection here is a run whose numbers would be wrong or unlabelled."""

    def _write(self, tmp_path: Path, document: Any) -> Path:
        target = tmp_path / "recorded.json"
        target.write_text(json.dumps(document))
        return target

    def _run(self, tmp_path: Path, modes: Any, **extra: Any) -> Path:
        return self._write(
            tmp_path, {"reranker": "stub/lexical-overlap@1", **extra, "modes": modes}
        )

    def test_a_string_where_an_id_list_belongs_is_rejected(
        self, tmp_path: Path
    ) -> None:
        # tuple("ab") is ("a", "b"): a string would invent two ids and score the row without
        # complaint, which is why this is not coerced.
        target = self._run(
            tmp_path,
            {
                "hybrid": [
                    {
                        "query_id": "q",
                        "subset": "dense",
                        "ranked_ids": "ab",
                        "expected_ids": ["a"],
                    }
                ]
            },
        )

        with pytest.raises(
            ValueError, match=r"field 'ranked_ids' must be a list of strings"
        ):
            bench.load_recorded(target)

    def test_a_non_string_id_is_rejected(self, tmp_path: Path) -> None:
        target = self._run(
            tmp_path,
            {
                "hybrid": [
                    {
                        "query_id": "q",
                        "subset": "dense",
                        "ranked_ids": [1],
                        "expected_ids": ["a"],
                    }
                ]
            },
        )

        with pytest.raises(
            ValueError, match=r"field 'ranked_ids' must be a list of strings"
        ):
            bench.load_recorded(target)

    def test_a_mode_that_is_not_a_list_is_named_in_the_error(
        self, tmp_path: Path
    ) -> None:
        target = self._run(tmp_path, {"hybrid": None})

        with pytest.raises(ValueError, match=r"mode 'hybrid' must be a list of rows"):
            bench.load_recorded(target)

    def test_a_sole_empty_mode_is_rejected(self, tmp_path: Path) -> None:
        # Nothing to compare against, so without this an empty run publishes ndcg 0.0 over zero
        # queries as if it were a measurement.
        target = self._run(tmp_path, {"empty": []})

        with pytest.raises(ValueError, match=r"mode 'empty' has no rows"):
            bench.load_recorded(target)

    def test_a_repeated_mode_name_is_rejected(self, tmp_path: Path) -> None:
        # json.loads keeps the last block, so a whole mode could vanish from a run that still
        # publishes as complete.
        target = tmp_path / "recorded.json"
        target.write_text('{"reranker": "r", "modes": {"hybrid": [], "hybrid": []}}')

        with pytest.raises(ValueError, match="duplicate key 'hybrid'"):
            bench.load_recorded(target)

    def test_a_recording_that_does_not_name_its_reranker_is_rejected(
        self, tmp_path: Path
    ) -> None:
        target = self._write(tmp_path, {"modes": {"hybrid": _perfect_outcomes()}})

        with pytest.raises(ValueError, match="does not name its reranker"):
            bench.load_recorded(target)

    def test_the_artifact_publishes_the_recordings_reranker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")
        target = self._run(
            tmp_path, {"hybrid": _perfect_outcomes()}, reranker="cross-encoder/tei@gpu"
        )

        assert bench.main(["bench", "--outcomes", str(target)]) == 0

        payload = json.loads((tmp_path / "out" / "modes-latest.json").read_text())
        assert payload["reranker"] == "cross-encoder/tei@gpu"

    def test_a_contradicting_reranker_flag_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")
        target = self._run(tmp_path, {"hybrid": _perfect_outcomes()})

        with pytest.raises(ValueError, match="contradicts the recording"):
            bench.main(
                ["bench", "--outcomes", str(target), "--reranker", "something-else"]
            )
        assert not (tmp_path / "out" / "modes-latest.json").exists()

    def test_an_agreeing_reranker_flag_is_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")
        target = self._run(tmp_path, {"hybrid": _perfect_outcomes()})

        assert (
            bench.main(
                [
                    "bench",
                    "--outcomes",
                    str(target),
                    "--reranker",
                    "stub/lexical-overlap@1",
                ]
            )
            == 0
        )

    def test_the_recorded_gold_set_wins_over_the_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")
        target = self._run(
            tmp_path, {"hybrid": _perfect_outcomes()}, gold_set="ranking_quality_v2"
        )

        assert bench.main(["bench", "--outcomes", str(target)]) == 0

        payload = json.loads((tmp_path / "out" / "modes-latest.json").read_text())
        assert payload["gold_set"] == "ranking_quality_v2"

    def test_a_failed_payload_write_leaves_the_previous_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bench, "INPUT_ROOT", tmp_path)
        monkeypatch.setattr(bench, "OUTPUT_DIR", tmp_path / "out")
        (tmp_path / "out").mkdir()
        artifact = tmp_path / "out" / "modes-latest.json"
        artifact.write_text('{"previous": true}\n')
        target = self._run(tmp_path, {"hybrid": _perfect_outcomes()})
        # A payload that cannot be serialised fails inside the write, after the temp file is
        # created: the old artifact must survive and no temp file may be left behind.
        monkeypatch.setattr(bench, "build_payload", lambda *a, **k: {"bad": {1, 2}})

        with pytest.raises(TypeError):
            bench.main(["bench", "--outcomes", str(target)])

        assert artifact.read_text() == '{"previous": true}\n'
        assert sorted(entry.name for entry in (tmp_path / "out").iterdir()) == [
            "modes-latest.json"
        ]


class TestDocumentShape:
    """The recording is a file: every wrong shape gets a message naming what is wrong."""

    def _write(self, tmp_path: Path, payload: Any) -> Path:
        target = tmp_path / "recorded.json"
        target.write_text(payload if isinstance(payload, str) else json.dumps(payload))
        return target

    def test_a_document_that_is_not_an_object_is_named(self, tmp_path: Path) -> None:
        target = self._write(tmp_path, [1, 2, 3])

        with pytest.raises(ValueError, match="is not a JSON object"):
            bench.load_recorded(target)

    def test_a_query_id_that_is_not_a_string_is_rejected(self, tmp_path: Path) -> None:
        target = self._write(
            tmp_path,
            {
                "reranker": "r",
                "modes": {
                    "hybrid": [
                        {"query_id": 7, "subset": "dense", "ranked_ids": [], "expected_ids": []}
                    ]
                },
            },
        )

        with pytest.raises(ValueError, match=r"field 'query_id' must be a string"):
            bench.load_recorded(target)

    def test_an_empty_reranker_is_rejected(self, tmp_path: Path) -> None:
        # An empty label would publish a number that names no reranker at all, which reads as
        # "no reranking happened" rather than "nobody recorded it".
        target = self._write(tmp_path, {"reranker": "", "modes": {"hybrid": _perfect_outcomes()}})

        with pytest.raises(ValueError, match="does not name its reranker"):
            bench.load_recorded(target)

    def test_a_non_string_gold_set_is_rejected(self, tmp_path: Path) -> None:
        target = self._write(
            tmp_path,
            {"reranker": "r", "gold_set": 2, "modes": {"hybrid": _perfect_outcomes()}},
        )

        with pytest.raises(ValueError, match="gold_set must be a string"):
            bench.load_recorded(target)

