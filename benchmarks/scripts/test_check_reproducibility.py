#!/usr/bin/env python3
"""Tests for the fail-closed reproducibility checker.

Every failure mode in the checker's contract gets a synthetic artifact that violates exactly
that rule, and every passing branch gets the smallest payload that must not be refused. The
committed artifacts are checked as they are, because "the checker passes on real data" is the
claim that matters most.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmark_test_support import ROOT, SCRIPTS, load_module

check = load_module("check_reproducibility", SCRIPTS / "check_reproducibility.py")
provenance = check.provenance
PUBLISHED = ROOT / "site" / "public" / "benchmarks"
MODES_PY = ROOT / "benchmarks" / "memory" / "ranking_quality" / "modes.py"
HNSW_CORPUS_HASH = provenance.corpus_identity("hnsw")[0]
OTHER_HASH = "0" * 64
# The checker refuses an artifact it cannot schema-validate, so anything asserting a clean run
# needs the validator. `benchmark-gate` (which runs this module) has no jsonschema installed;
# those tests skip there rather than pass silently, and the rest still run.
NEEDS_JSONSCHEMA = unittest.skipUnless(
    check.jsonschema is not None,
    "needs jsonschema: pip install -r .github/requirements/jsonschema.txt",
)


def _hnsw_result(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "corpus_size": 1000,
        "query_count": 10,
        "recall_at_10": 0.9,
        "latency_ms_p50": 1.0,
        "latency_ms_p95": 2.0,
        "latency_ms_p99": 3.0,
        "ef_search": 64,
    }
    result.update(overrides)
    return result


def _recorded(**overrides: object) -> dict[str, object]:
    block: dict[str, object] = {
        "status": "recorded",
        "producer": provenance.PRODUCER,
        "runner_cpu_model": "Test CPU 9000",
        "runner_cpu_count": 4,
        "runner_ram_mib": 8192,
        "corpus_hash": HNSW_CORPUS_HASH,
        "corpus_hash_algo": "sha256",
        "corpus_manifest": "pgvector|synth.py=x|corpus.py=y|dim=1024,active=64",
        "corpus_status": "current",
        "dirty": False,
    }
    block.update(overrides)
    return block


def _hnsw_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "sha": "a" * 40,
        "short_sha": "a" * 7,
        "timestamp": "2026-11-12T00:00:00+00:00",
        "branch": "main",
        "run_number": 1,
        "run_url": "https://example.invalid/actions/runs/1",
        "methodology": {"note": "synthetic"},
        "mean_recall_at_10": 0.97,
        "status": "pass",
        "results": [_hnsw_result()],
        "provenance": _recorded(),
    }
    run.update(overrides)
    return run


def _unrecorded_run(sha: str = "c" * 40, **overrides: object) -> dict[str, object]:
    run = _hnsw_run(sha=sha, short_sha=sha[:7], **overrides)
    del run["provenance"]
    return run


def _ranking_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "sha": "b" * 40,
        "short_sha": "b" * 7,
        "timestamp": "2026-11-12T00:00:00+00:00",
        "branch": "main",
        "run_number": 2,
        "run_url": "https://example.invalid/actions/runs/2",
        "metrics": {"precision_at_5": 0.8, "recall_at_10": 0.7, "mrr": 0.6},
        "status": "pass",
        "gold_set": "v1",
    }
    run.update(overrides)
    return run


def _payload(benchmark: str, *runs: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "benchmark": benchmark, "runs": list(runs)}


def _hnsw(*runs: dict[str, object]) -> dict[str, object]:
    return _payload("hnsw_recall_latency", *runs)


def _ranking(*runs: dict[str, object]) -> dict[str, object]:
    return _payload("ranking_quality", *runs)


class CheckerCase(unittest.TestCase):
    """Writes artifacts under test into a temporary directory and reads the report."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def write(self, payload: object, name: str = "hnsw-benchmark-data.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def report_for(self, payload: object, name: str = "hnsw-benchmark-data.json") -> check.Report:
        report = check.Report()
        check.check_path(self.write(payload, name), report)
        return report

    def content_problems(
        self, payload: object, name: str = "hnsw-benchmark-data.json"
    ) -> list[str]:
        """The provenance rules only, without the JSON Schema pass.

        Positive cases use this so they keep running where jsonschema is not installed; the
        schema pass has its own tests behind ``NEEDS_JSONSCHEMA``.
        """
        return check._check_payload(payload, check._kind(Path(name)))

    def assert_problem(self, report: check.Report, needle: str) -> None:
        problems = report.problems
        self.assertTrue(
            any(needle in problem for problem in problems),
            f"expected a problem containing {needle!r}, got {problems}",
        )

    def assert_clean(self, payload: object, name: str = "hnsw-benchmark-data.json") -> None:
        problems = self.content_problems(payload, name)
        self.assertEqual(problems, [], f"expected no problems, got {problems}")


class TestCommittedArtifacts(CheckerCase):
    @NEEDS_JSONSCHEMA
    def test_every_published_artifact_passes(self) -> None:
        paths = check.default_paths()
        self.assertEqual(len(paths), 4)
        report = check.check_paths(paths)

        self.assertEqual(report.problems, [], f"expected no problems, got {report.problems}")
        self.assertGreater(report.run_count, 0)

    def test_every_committed_run_is_counted_as_unrecorded(self) -> None:
        report = check.check_paths(check.default_paths())

        self.assertEqual(report.unrecorded, report.run_count)
        self.assertEqual(len(report.warnings), 4)

    @NEEDS_JSONSCHEMA
    def test_main_exits_zero_and_prints_the_unrecorded_count(self) -> None:
        paths = check.default_paths()
        unrecorded = check.check_paths(paths).unrecorded
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main([str(path) for path in paths])

        self.assertEqual(code, 0)
        self.assertIn("0 problem(s)", out.getvalue())
        self.assertIn(f"{unrecorded} unrecorded run(s)", out.getvalue())
        self.assertIn("Warning:", err.getvalue())


class TestIdentity(CheckerCase):
    def test_a_sha_that_is_not_40_lowercase_hex_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(sha="A" * 40, short_sha="A" * 7)))

        self.assert_problem(report, "runs[0].sha: 'AAAAAAA")
        self.assert_problem(report, "is not 40 lowercase hex characters")

    def test_a_short_sha_that_is_not_the_prefix_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(short_sha="deadbee")))

        self.assert_problem(report, "runs[0].short_sha: 'deadbee' != sha[:7] 'aaaaaaa'")

    def test_a_duplicate_sha_fails(self) -> None:
        report = self.report_for(_hnsw(_unrecorded_run(sha="a" * 40), _hnsw_run(run_number=2)))

        self.assert_problem(report, "runs[1].sha: duplicate aaa")

    def test_an_empty_run_url_on_a_recorded_run_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(run_url="")))

        self.assert_problem(
            report, "runs[0].run_url: empty on a run with provenance.status='recorded'"
        )

    def test_an_empty_run_url_on_an_unrecorded_run_is_not_a_problem(self) -> None:
        self.assert_clean(_hnsw(_unrecorded_run(run_url="")))


class TestDirtyTree(CheckerCase):
    def test_a_dirty_recorded_run_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(provenance=_recorded(dirty=True))))

        self.assert_problem(report, "runs[0].provenance.dirty: true")

    def test_a_dirty_unrecorded_run_also_fails(self) -> None:
        report = self.report_for(
            _hnsw(_hnsw_run(provenance={"status": "unrecorded", "dirty": True}))
        )

        self.assert_problem(report, "runs[0].provenance.dirty: true")


class TestCorpusIdentity(CheckerCase):
    def test_a_matching_hash_declared_current_passes(self) -> None:
        self.assert_clean(_hnsw(_hnsw_run()))

    def test_a_matching_hash_declared_stale_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(provenance=_recorded(corpus_status="stale"))))

        self.assert_problem(
            report, "runs[0].provenance.corpus_status: 'stale' but corpus_hash matches"
        )

    def test_a_different_hash_declared_current_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(provenance=_recorded(corpus_hash=OTHER_HASH))))

        self.assert_problem(
            report, "runs[0].provenance.corpus_status: 'current' but corpus_hash '0"
        )
        self.assert_problem(
            report, f"differs from the checked-out hnsw corpus ({HNSW_CORPUS_HASH})"
        )

    def test_a_different_hash_declared_stale_passes(self) -> None:
        self.assert_clean(
            _hnsw(_hnsw_run(provenance=_recorded(corpus_hash=OTHER_HASH, corpus_status="stale")))
        )

    def test_only_the_newest_recorded_run_declares_the_corpus(self) -> None:
        stale_history = _hnsw_run(
            sha="d" * 40,
            short_sha="d" * 7,
            provenance=_recorded(corpus_hash=OTHER_HASH, corpus_status="stale"),
        )
        self.assert_clean(_hnsw(_hnsw_run(run_number=2), stale_history))

    def test_a_recorded_run_on_a_corpus_less_kind_fails(self) -> None:
        run = _hnsw_run()
        report = self.report_for(
            _payload("extraction_quality", run), "extraction-quality-benchmark-data.json"
        )

        self.assert_problem(report, "recorded on an artifact kind with no corpus identity")


class TestPercentiles(CheckerCase):
    def test_a_p50_above_its_p95_fails(self) -> None:
        report = self.report_for(
            _hnsw(_hnsw_run(results=[_hnsw_result(latency_ms_p50=5.0, latency_ms_p95=4.0)]))
        )

        self.assert_problem(report, "runs[0].results[0].latency_ms: p50 5.0 > p95 4.0")

    def test_a_p95_above_its_p99_fails(self) -> None:
        report = self.report_for(
            _hnsw(_hnsw_run(results=[_hnsw_result(latency_ms_p95=9.0, latency_ms_p99=8.0)]))
        )

        self.assert_problem(report, "runs[0].results[0].latency_ms: p95 9.0 > p99 8.0")

    def test_a_p95_below_its_ci_low_fails(self) -> None:
        result = _hnsw_result(latency_ms_p95_ci_low=2.5, latency_ms_p95_ci_high=3.5)
        report = self.report_for(_hnsw(_hnsw_run(results=[result])))

        self.assert_problem(report, "latency_ms: p95 2.0 below ci_low 2.5")

    def test_a_p95_above_its_ci_high_fails(self) -> None:
        result = _hnsw_result(latency_ms_p95_ci_low=1.0, latency_ms_p95_ci_high=1.5)
        report = self.report_for(_hnsw(_hnsw_run(results=[result])))

        self.assert_problem(report, "latency_ms: p95 2.0 above ci_high 1.5")

    def test_an_ordered_result_with_a_containing_interval_passes(self) -> None:
        result = _hnsw_result(latency_ms_p95_ci_low=1.9, latency_ms_p95_ci_high=2.1)
        self.assert_clean(_hnsw(_hnsw_run(results=[result])))

    def test_a_percentile_that_is_not_a_number_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(results=[_hnsw_result(latency_ms_p95="2.0")])))

        self.assert_problem(report, "latency_ms_p95: not a number ('2.0')")


class TestRanking(CheckerCase):
    def test_a_known_gold_set_passes(self) -> None:
        self.assert_clean(_ranking(_ranking_run()), "ranking-quality-benchmark-data.json")

    def test_an_unknown_gold_set_fails(self) -> None:
        report = self.report_for(
            _ranking(_ranking_run(gold_set="v3")), "ranking-quality-benchmark-data.json"
        )

        self.assert_problem(report, "runs[0].gold_set: 'v3' is not one of")

    def test_the_v2_gold_set_is_accepted(self) -> None:
        self.assert_clean(
            _ranking(_ranking_run(gold_set="ranking_quality_v2")),
            "ranking-quality-benchmark-data.json",
        )

    def test_an_unknown_mode_fails(self) -> None:
        run = _ranking_run(gate_summary={"modes": {"hybrid": {}, "sparse": {}}})
        report = self.report_for(_ranking(run), "ranking-quality-benchmark-data.json")

        self.assert_problem(report, "runs[0].modes: unknown mode(s) ['sparse']")

    def test_a_missing_required_mode_fails(self) -> None:
        run = _ranking_run(gate_summary={"modes": {"hybrid_rerank": {}}})
        report = self.report_for(_ranking(run), "ranking-quality-benchmark-data.json")

        self.assert_problem(report, "runs[0].modes: missing required mode(s) ['full_graph']")

    def test_every_defined_mode_passes(self) -> None:
        modes = {name: {} for name in sorted(check.MODE_NAMES)}
        run = _ranking_run(gate_summary={"modes": modes})

        self.assert_clean(_ranking(run), "ranking-quality-benchmark-data.json")

    def test_modes_that_are_not_an_object_fail(self) -> None:
        run = _ranking_run(gate_summary={"modes": ["hybrid_rerank", "full_graph"]})
        report = self.report_for(_ranking(run), "ranking-quality-benchmark-data.json")

        self.assert_problem(report, "runs[0].modes: must be an object keyed by mode name")

    def test_the_mode_names_match_the_runner(self) -> None:
        declared = set(re.findall(r'name="([a-z_]+)"', MODES_PY.read_text(encoding="utf-8")))

        self.assertEqual(declared, set(check.MODE_NAMES))


class TestUnrecordedWarnings(CheckerCase):
    @NEEDS_JSONSCHEMA
    def test_an_unrecorded_run_is_a_warning_not_a_failure(self) -> None:
        payload = _hnsw(_unrecorded_run())
        report = self.report_for(payload)

        self.assertTrue(report.ok)
        self.assertEqual(report.unrecorded, 1)
        self.assert_clean(payload)
        self.assertEqual(len(report.warnings), 1)

    @NEEDS_JSONSCHEMA
    def test_the_warning_states_that_the_run_is_not_evidence(self) -> None:
        run = _hnsw_run(provenance={"status": "unrecorded"})
        report = self.report_for(_hnsw(run))

        self.assertTrue(report.ok)
        self.assertIn("1 of 1 run(s) are unrecorded", report.warnings[0])
        self.assertIn("not reproducible evidence", report.warnings[0])

    @NEEDS_JSONSCHEMA
    def test_mixed_artifacts_count_only_unrecorded_runs(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(run_number=2), _unrecorded_run(run_number=3)))

        self.assertTrue(report.ok)
        self.assertEqual(report.unrecorded, 1)


class TestFailClosed(CheckerCase):
    def test_a_missing_file_fails(self) -> None:
        report = check.Report()
        check.check_path(self.tmp / "hnsw-benchmark-data.json", report)

        self.assert_problem(report, "cannot read artifact")

    def test_invalid_json_fails(self) -> None:
        path = self.tmp / "hnsw-benchmark-data.json"
        path.write_text("{not json", encoding="utf-8")
        report = check.Report()
        check.check_path(path, report)

        self.assert_problem(report, "invalid JSON")

    def test_a_non_object_root_fails(self) -> None:
        self.assert_problem(self.report_for([]), "artifact root must be a JSON object")

    def test_an_unknown_artifact_kind_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run()), "proxy-benchmark-data.json")

        self.assert_problem(report, "unknown artifact kind 'proxy'; known kinds:")
        self.assert_problem(report, "hnsw, ranking-quality")

    def test_a_missing_schema_fails(self) -> None:
        with mock.patch.object(check, "SCHEMA_DIR", self.tmp):
            report = self.report_for(_hnsw(_hnsw_run()))

        self.assert_problem(report, "missing schema hnsw-benchmark-data.schema.json")

    @NEEDS_JSONSCHEMA
    def test_a_schema_violation_fails(self) -> None:
        report = self.report_for(_hnsw(_hnsw_run(run_number="one")))

        self.assert_problem(report, "schema: runs[0].run_number:")

    def test_a_missing_runs_array_fails(self) -> None:
        payload = {"schema_version": 1, "benchmark": "hnsw_recall_latency"}

        self.assert_problem(self.report_for(payload), "runs: missing or not an array")


class TestRealArtifactViolation(CheckerCase):
    def test_swapping_p95_and_p99_in_a_real_run_fails(self) -> None:
        copy = self.tmp / "hnsw-benchmark-data.json"
        shutil.copyfile(PUBLISHED / "hnsw-benchmark-data.json", copy)
        payload = json.loads(copy.read_text(encoding="utf-8"))
        result = payload["runs"][5]["results"][0]
        result["latency_ms_p95"], result["latency_ms_p99"] = (
            result["latency_ms_p99"],
            result["latency_ms_p95"],
        )
        copy.write_text(json.dumps(payload), encoding="utf-8")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main([str(copy)])

        self.assertEqual(code, 1)
        self.assertIn("runs[5].results[0].latency_ms: p95", err.getvalue())
        self.assertIn("> p99", err.getvalue())


if __name__ == "__main__":
    unittest.main()
