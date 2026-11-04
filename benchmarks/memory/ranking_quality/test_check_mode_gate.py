"""Tests for the multi-mode gate CLI: what it compares, and what it refuses to compare.

The interesting behaviour is the refusal. A gate that compares a run against a baseline from a
different corpus or a different reranker reports a pass that means nothing, and no assertion in
`gate_modes` can catch it because the numbers are well formed.
"""

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

import check_mode_gate as gate_cli

GOLD_SET = "ranking_quality_v2"
RERANKER = "stub/lexical-overlap@1"
MODES = ("dense_only", "hybrid", "hybrid_rerank", "full_graph")


def _mode_row(overall: float, *, non_graph: float | None = None) -> dict[str, Any]:
    return {
        "ndcg_at_10": overall,
        "non_graph_ndcg_at_10": overall if non_graph is None else non_graph,
        "graph_ndcg_at_10": overall,
        "query_count": 30,
        "per_subset_counts": {"dense": 10, "lexical": 10, "graph": 10},
    }


def _artifact(**scores: float) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "benchmark": "ranking_quality",
        "gold_set": GOLD_SET,
        "reranker": RERANKER,
        "modes": {name: _mode_row(scores.get(name, 0.80)) for name in MODES},
    }


def _baseline(**scores: float) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark": "ranking_quality",
        "gold_set": GOLD_SET,
        "reranker": RERANKER,
        "baseline": {name: scores.get(name, 0.80) for name in MODES},
    }


def _write(directory: Path, name: str, document: Any) -> Path:
    path = directory / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class TestLoadArtifact:
    def test_a_well_formed_artifact_becomes_mode_results(self, tmp_path: Path) -> None:
        artifact = gate_cli.load_artifact(_write(tmp_path, "m.json", _artifact()))

        assert artifact.gold_set == GOLD_SET
        assert artifact.reranker == RERANKER
        assert set(artifact.results) == set(MODES)
        assert artifact.results["hybrid"].query_count == 30

    def test_an_artifact_without_modes_is_rejected(self, tmp_path: Path) -> None:
        document = _artifact()
        document["modes"] = {}

        with pytest.raises(gate_cli.GateInputError, match="no modes to gate"):
            gate_cli.load_artifact(_write(tmp_path, "m.json", document))

    def test_an_artifact_without_a_reranker_is_rejected(self, tmp_path: Path) -> None:
        # Without it there is nothing to compare against the baseline's reranker.
        document = _artifact()
        del document["reranker"]

        with pytest.raises(gate_cli.GateInputError, match="does not name its reranker"):
            gate_cli.load_artifact(_write(tmp_path, "m.json", document))

    def test_a_boolean_score_is_rejected(self, tmp_path: Path) -> None:
        # bool is an int, so `true` would slide through as 1.0 and read as a perfect score.
        document = _artifact()
        document["modes"]["hybrid"]["ndcg_at_10"] = True

        with pytest.raises(gate_cli.GateInputError, match="must be a number"):
            gate_cli.load_artifact(_write(tmp_path, "m.json", document))

    def test_a_score_that_is_a_string_is_rejected(self, tmp_path: Path) -> None:
        document = _artifact()
        document["modes"]["hybrid"]["ndcg_at_10"] = "0.8"

        with pytest.raises(gate_cli.GateInputError, match="must be a number"):
            gate_cli.load_artifact(_write(tmp_path, "m.json", document))

    def test_a_mode_that_is_not_an_object_is_named(self, tmp_path: Path) -> None:
        document = _artifact()
        document["modes"]["hybrid"] = [1, 2]

        with pytest.raises(gate_cli.GateInputError, match="'hybrid' is not an object"):
            gate_cli.load_artifact(_write(tmp_path, "m.json", document))

    def test_a_document_that_is_not_json_is_reported_with_its_name(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "m.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(gate_cli.GateInputError, match="m.json"):
            gate_cli.load_artifact(path)


class TestLoadBaseline:
    def test_a_well_formed_baseline_is_read(self, tmp_path: Path) -> None:
        baseline = gate_cli.load_baseline(_write(tmp_path, "b.json", _baseline()))

        assert baseline.scores == dict.fromkeys(MODES, 0.80)

    def test_a_baseline_without_scores_is_rejected(self, tmp_path: Path) -> None:
        document = _baseline()
        document["baseline"] = {}

        with pytest.raises(
            gate_cli.GateInputError, match="no baseline to compare against"
        ):
            gate_cli.load_baseline(_write(tmp_path, "b.json", document))


class TestSameExperiment:
    def _parsed(
        self, tmp_path: Path, artifact: dict[str, Any], baseline: dict[str, Any]
    ) -> tuple[Any, Any]:
        return (
            gate_cli.load_artifact(_write(tmp_path, "m.json", artifact)),
            gate_cli.load_baseline(_write(tmp_path, "b.json", baseline)),
        )

    def test_matching_provenance_is_accepted(self, tmp_path: Path) -> None:
        gate_cli.require_same_experiment(
            *self._parsed(tmp_path, _artifact(), _baseline())
        )

    def test_another_gold_set_is_refused(self, tmp_path: Path) -> None:
        document = _baseline()
        document["gold_set"] = "ranking_quality_v1"

        with pytest.raises(gate_cli.GateInputError, match="was not the baseline's"):
            gate_cli.require_same_experiment(
                *self._parsed(tmp_path, _artifact(), document)
            )

    def test_another_reranker_is_refused(self, tmp_path: Path) -> None:
        # A cross-encoder's numbers are not a threshold for a fused run's numbers.
        document = _baseline()
        document["reranker"] = "bge-reranker-v2-m3"

        with pytest.raises(gate_cli.GateInputError, match="reranker"):
            gate_cli.require_same_experiment(
                *self._parsed(tmp_path, _artifact(), document)
            )


class TestMain:
    def _run(
        self,
        tmp_path: Path,
        artifact: dict[str, Any],
        baseline: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[int, dict[str, Any]]:
        # The CLI confines both inputs to the benchmark directory; the test lives elsewhere.
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        report = tmp_path / "out" / "modes-gate.json"
        code = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(_write(tmp_path, "m.json", artifact)),
                "--baseline",
                str(_write(tmp_path, "b.json", baseline)),
                "--report-out",
                str(report),
            ]
        )
        return code, json.loads(report.read_text(encoding="utf-8"))

    def test_a_run_at_its_baseline_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, report = self._run(tmp_path, _artifact(), _baseline(), monkeypatch)

        assert code == 0
        assert report["status"] == "pass"
        assert report["failures"] == []

    def test_a_run_three_points_below_its_baseline_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact = _artifact(hybrid=0.80)
        artifact["modes"]["hybrid"] = _mode_row(0.70)

        code, report = self._run(
            tmp_path, artifact, _baseline(hybrid=0.80), monkeypatch
        )

        assert code == 1
        assert report["status"] == "fail"
        assert report["failures"][0]["check"] == "baseline drop"
        assert report["failures"][0]["mode"] == "hybrid"

    def test_a_failing_gate_still_writes_its_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The report is what the job uploads; a gate that only fails the build cannot be read
        # afterwards.
        artifact = _artifact()
        artifact["modes"]["full_graph"] = _mode_row(0.50)

        _code, report = self._run(tmp_path, artifact, _baseline(), monkeypatch)

        assert report["status"] == "fail"
        assert report["modes"]["full_graph"]["overall"] == 0.50

    def test_a_missing_mode_fails_coverage_rather_than_being_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact = _artifact()
        del artifact["modes"]["full_graph"]

        code, report = self._run(tmp_path, artifact, _baseline(), monkeypatch)

        assert code == 1
        assert any(failure["check"] == "coverage" for failure in report["failures"])

    def test_the_series_graph_gap_is_enforced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # full_graph gives back three points of non-graph nDCG; the allowance is two.
        artifact = _artifact()
        artifact["modes"]["hybrid_rerank"] = _mode_row(0.90, non_graph=0.90)
        artifact["modes"]["full_graph"] = _mode_row(0.90, non_graph=0.87)

        code, report = self._run(tmp_path, artifact, _baseline(), monkeypatch)

        assert code == 1
        assert any(failure["check"] == "graph gap" for failure in report["failures"])


class TestGraphComparisonFlag:
    def test_identical_modes_are_reported_as_not_distinguished(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two equal rows are not evidence that suppression helps; the report says so instead of
        # leaving a reader to notice the equality and guess.
        code, report = TestMain()._run(tmp_path, _artifact(), _baseline(), monkeypatch)

        assert code == 0
        assert report["graph_mode_distinguished"] is False

    def test_a_subject_mode_that_moves_is_reported_as_distinguished(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact = _artifact()
        artifact["modes"]["full_graph"] = _mode_row(0.85, non_graph=0.80)

        _code, report = TestMain()._run(tmp_path, artifact, _baseline(), monkeypatch)

        assert report["graph_mode_distinguished"] is True

    def test_a_missing_reference_mode_leaves_the_question_unanswered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact = _artifact()
        del artifact["modes"]["hybrid_rerank"]

        _code, report = TestMain()._run(tmp_path, artifact, _baseline(), monkeypatch)

        assert report["graph_mode_distinguished"] is None


class TestCommittedBaseline:
    def test_the_baseline_covers_every_mode_on_the_v2_corpus(self) -> None:
        baseline = gate_cli.load_baseline(gate_cli.BASELINE_PATH)

        assert set(baseline.scores) == set(MODES)
        assert baseline.gold_set == GOLD_SET
        assert all(0.0 <= score <= 1.0 for score in baseline.scores.values())

    def test_the_baseline_names_the_reranker_it_was_measured_with(self) -> None:
        # A baseline recorded with a cross-encoder would silently become the threshold for the
        # stub's numbers, and nothing downstream would notice.
        baseline = gate_cli.load_baseline(gate_cli.BASELINE_PATH)

        assert baseline.reranker == RERANKER


class TestRejectedRunsStillReport:
    def test_a_provenance_mismatch_writes_a_failed_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # CI fails correctly either way; the difference is whether the reviewer has to open the
        # job log to find out why.
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        baseline = _baseline()
        baseline["reranker"] = "bge-reranker-v2-m3"
        report_path = tmp_path / "out" / "modes-gate.json"

        code = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(_write(tmp_path, "m.json", _artifact())),
                "--baseline",
                str(_write(tmp_path, "b.json", baseline)),
                "--report-out",
                str(report_path),
            ]
        )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert code == 1
        assert report["status"] == "fail"
        assert report["failures"][0]["check"] == "provenance"
        # Both files parsed, so the numbers are still shown next to the reason they were refused.
        assert report["modes"]["hybrid"]["overall"] == 0.80

    def test_an_unreadable_artifact_writes_a_failed_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        broken = tmp_path / "m.json"
        broken.write_text("{not json", encoding="utf-8")
        report_path = tmp_path / "out" / "modes-gate.json"

        code = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(broken),
                "--baseline",
                str(_write(tmp_path, "b.json", _baseline())),
                "--report-out",
                str(report_path),
            ]
        )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert code == 2
        assert report["status"] == "fail"
        assert report["failures"][0]["check"] == "input"

    def test_a_refused_input_exits_differently_from_a_regression(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `2` means "we did not measure this"; `1` means "the measurement moved". A caller that
        # cannot tell them apart treats a broken gold set as a performance drop.
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        broken = tmp_path / "m.json"
        broken.write_text("{not json", encoding="utf-8")
        refused = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(broken),
                "--baseline",
                str(_write(tmp_path, "b.json", _baseline())),
                "--report-out",
                str(tmp_path / "out" / "refused.json"),
            ]
        )
        artifact = _artifact()
        artifact["modes"]["hybrid"] = _mode_row(0.70)
        regressed = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(_write(tmp_path, "m2.json", artifact)),
                "--baseline",
                str(_write(tmp_path, "b2.json", _baseline())),
                "--report-out",
                str(tmp_path / "out" / "regressed.json"),
            ]
        )

        assert (refused, regressed) == (2, 1)


class TestMissingInputs:
    def test_a_missing_artifact_still_writes_a_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The ordinary case when the benchmark step failed: the gate runs, finds no artifact, and
        # owes the job the same verdict it would write for any other unreadable input.
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        report_path = tmp_path / "out" / "modes-gate.json"

        code = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(tmp_path / "never-written.json"),
                "--baseline",
                str(_write(tmp_path, "b.json", _baseline())),
                "--report-out",
                str(report_path),
            ]
        )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert code == 2
        assert report["status"] == "fail"
        assert report["failures"][0]["check"] == "input"
        assert "never-written.json" in report["failures"][0]["detail"]

    def test_a_missing_baseline_still_writes_a_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gate_cli, "_RANK_DIR", tmp_path)
        report_path = tmp_path / "out" / "modes-gate.json"

        code = gate_cli.main(
            [
                "gate",
                "--artifact",
                str(_write(tmp_path, "m.json", _artifact())),
                "--baseline",
                str(tmp_path / "no-baseline.json"),
                "--report-out",
                str(report_path),
            ]
        )

        assert code == 2
        assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "fail"
