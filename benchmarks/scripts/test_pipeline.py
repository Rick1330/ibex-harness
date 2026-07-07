#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "benchmarks" / "scripts"
TESTDATA = ROOT / "benchmarks" / "testdata"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


aggregate_metrics = load_module("aggregate_metrics", SCRIPTS / "aggregate_metrics.py")
regression_gate = load_module("regression_gate", SCRIPTS / "regression_gate.py")
build_benchmark_data = load_module("build_benchmark_data", SCRIPTS / "build_benchmark_data.py")
generate_badge = load_module("generate_badge", SCRIPTS / "generate_badge.py")
validate_published_data = load_module(
    "validate_published_data",
    SCRIPTS / "validate_published_data.py",
)
benchmark_constants = load_module("benchmark_constants", SCRIPTS / "benchmark_constants.py")


def _minimal_benchmark_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "sha": "a" * 40,
        "short_sha": "aaaaaaa",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "branch": "main",
        "status": "pass",
        "k6": {"p99_ms": 4.0, "error_rate": 0.0},
    }
    run.update(overrides)
    return run


def _assert_validate_rejects(payload: dict[str, object]) -> None:
    try:
        validate_published_data.validate_payload(payload)
    except SystemExit:
        return
    raise AssertionError("expected validate_payload to raise SystemExit")


def _invalid_payload_cases() -> list[tuple[str, dict[str, object]]]:
    proxy_bench = benchmark_constants.PROXY_OVERHEAD_BENCHMARK
    return [
        (
            "empty baseline_sha",
            {
                "schema_version": 1,
                "baseline_sha": "",
                "runs": [_minimal_benchmark_run()],
            },
        ),
        (
            "run_id as run_number",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        pr_number=None,
                        run_number=28594093144,
                        run_url="https://github.com/Rick1330/ibex-harness/actions/runs/28594093144",
                    ),
                ],
            },
        ),
        (
            f"missing {proxy_bench}",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        go_benchmarks={"BenchmarkOther": {"ns_per_op": 100.0}},
                    ),
                ],
            },
        ),
        (
            "non-positive ns_per_op",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        go_benchmarks={proxy_bench: {"ns_per_op": 0}},
                    ),
                ],
            },
        ),
    ]


class AggregateMetricsTests(unittest.TestCase):
    def test_parse_go_bench_line_extracts_metrics(self) -> None:
        line = "BenchmarkProxyOverhead-8   	  200000	      8500 ns/op	     512 B/op	       8 allocs/op"
        row = aggregate_metrics.parse_go_bench_line(line)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["name"], "BenchmarkProxyOverhead")
        self.assertAlmostEqual(row["metrics"]["ns_per_op"], 8500.0)
        self.assertAlmostEqual(row["metrics"]["bytes_per_op"], 512.0)
        self.assertAlmostEqual(row["metrics"]["allocs_per_op"], 8.0)

    def test_parse_go_bench_ignores_non_bench_lines(self) -> None:
        self.assertIsNone(aggregate_metrics.parse_go_bench_line("PASS"))

    def test_parse_k6_summary_reads_percentiles(self) -> None:
        k6 = aggregate_metrics.parse_k6_summary(TESTDATA / "k6-summary-pass.json")
        self.assertAlmostEqual(k6["p99_ms"], 12.0)
        self.assertAlmostEqual(k6["error_rate"], 0.0)
        self.assertAlmostEqual(k6["req_per_s"], 850.5)

    def test_parse_k6_summary_reads_flat_v053_export(self) -> None:
        k6 = aggregate_metrics.parse_k6_summary(TESTDATA / "k6-summary-v053.json")
        self.assertAlmostEqual(k6["p99_ms"], 1.24)
        self.assertAlmostEqual(k6["p50_ms"], 0.35)
        self.assertAlmostEqual(k6["req_per_s"], 8771.65)
        self.assertAlmostEqual(k6["check_rate"], 1.0)
        self.assertAlmostEqual(k6["error_rate"], 0.0)

    def test_parse_k6_summary_reads_local_docker_export(self) -> None:
        export = ROOT / "benchmarks/output/k6-test-export.json"
        if not export.exists():
            self.skipTest("local k6 export not available")
        k6 = aggregate_metrics.parse_k6_summary(export)
        self.assertGreater(k6["req_per_s"], 0.0)

    def test_safe_int_rejects_invalid_runner_vcpu(self) -> None:
        self.assertEqual(aggregate_metrics.safe_int("not-a-number", 4), 4)

    def test_stage_breakdown_maps_go_bench_to_us(self) -> None:
        go_bench = aggregate_metrics.parse_go_bench(TESTDATA / "go-bench-sample.txt")
        stages = aggregate_metrics.stage_breakdown(go_bench)
        self.assertGreater(stages["synthetic_total_us"], 0.0)
        self.assertGreater(stages["synthetic_auth_us"], 0.0)

    def test_parse_pr_number_reads_env(self) -> None:
        import os

        prior = os.environ.get("GITHUB_EVENT_PULL_REQUEST_NUMBER")
        try:
            os.environ["GITHUB_EVENT_PULL_REQUEST_NUMBER"] = "176"
            self.assertEqual(aggregate_metrics.parse_pr_number(), 176)
            os.environ.pop("GITHUB_EVENT_PULL_REQUEST_NUMBER", None)
            self.assertIsNone(aggregate_metrics.parse_pr_number())
        finally:
            if prior is None:
                os.environ.pop("GITHUB_EVENT_PULL_REQUEST_NUMBER", None)
            else:
                os.environ["GITHUB_EVENT_PULL_REQUEST_NUMBER"] = prior


class RegressionGateTests(unittest.TestCase):
    def test_read_float_coerces_and_falls_back(self) -> None:
        self.assertAlmostEqual(regression_gate.read_float("12.5"), 12.5)
        self.assertAlmostEqual(regression_gate.read_float("bad", 3.0), 3.0)

    def test_pct_change_handles_zero_baseline(self) -> None:
        self.assertEqual(regression_gate.pct_change(10.0, 0.0), 0.0)

    def test_build_checks_passes_within_policy(self) -> None:
        latest = regression_gate.normalize_latest(json.loads((TESTDATA / "latest-pass.json").read_text()))
        baseline = regression_gate.normalize_baseline(
            json.loads((ROOT / "benchmarks/data-schema/baseline.json").read_text())
        )
        checks = regression_gate.build_checks(latest, baseline)
        self.assertTrue(all(passed for _, _, _, passed in checks))

    def test_build_checks_fails_on_high_p99_and_error_rate(self) -> None:
        latest = regression_gate.normalize_latest(json.loads((TESTDATA / "latest-fail.json").read_text()))
        baseline = regression_gate.normalize_baseline(
            json.loads((ROOT / "benchmarks/data-schema/baseline.json").read_text())
        )
        checks = regression_gate.build_checks(latest, baseline)
        failed = [name for name, _, _, passed in checks if not passed]
        self.assertIn("k6 p99 SLA", failed)
        self.assertIn("error rate", failed)

    def test_main_exits_nonzero_on_failed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            shutil.copy(TESTDATA / "latest-fail.json", out / "latest.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", out / "baseline.json")
            regression_gate.LATEST_PATH = out / "latest.json"
            regression_gate.BASELINE_PATH = out / "baseline.json"
            self.assertEqual(regression_gate.main(), 1)

    def test_main_exits_zero_on_passing_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            shutil.copy(TESTDATA / "latest-pass.json", out / "latest.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", out / "baseline.json")
            regression_gate.LATEST_PATH = out / "latest.json"
            regression_gate.BASELINE_PATH = out / "baseline.json"
            self.assertEqual(regression_gate.main(), 0)


class BuildBenchmarkDataTests(unittest.TestCase):
    def test_merge_runs_replaces_same_pr_number(self) -> None:
        prev = [
            {"sha": "aaa", "pr_number": 176, "branch": "feature"},
            {"sha": "bbb", "pr_number": None, "branch": "main"},
        ]
        new_run = {"sha": "ccc", "pr_number": 176, "branch": "feature"}
        merged = build_benchmark_data.merge_runs(prev, new_run)
        self.assertEqual([run["sha"] for run in merged], ["ccc", "bbb"])

    def test_merge_runs_drops_provisional_pr_rows_on_main(self) -> None:
        prev = [
            {"sha": "aaa", "pr_number": 176, "branch": "feature"},
            {"sha": "bbb", "pr_number": None, "branch": "main"},
        ]
        new_run = {"sha": "ddd", "pr_number": None, "branch": "main"}
        merged = build_benchmark_data.merge_runs(prev, new_run)
        self.assertEqual([run["sha"] for run in merged], ["ddd", "bbb"])

    def test_safe_int_preserves_zero_runner_vcpus(self) -> None:
        self.assertEqual(build_benchmark_data.safe_int(0, 2), 0)
        self.assertEqual(build_benchmark_data.safe_int(None, 2), 2)
        self.assertEqual(
            build_benchmark_data.build_runner_metadata({"runner_vcpus": 0})["runner_vcpus"],
            0,
        )

    def test_build_benchmark_data_includes_run_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "benchmarks" / "output"
            data_schema = root / "benchmarks" / "data-schema"
            out.mkdir(parents=True)
            data_schema.mkdir(parents=True)
            shutil.copy(TESTDATA / "latest-pass.json", out / "latest.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", data_schema / "baseline.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", out / "baseline.json")
            shutil.copy(TESTDATA / "benchstat-sample.json", out / "benchstat.json")
            (out / "prev-benchmark-data.json").write_text(
                '{"schema_version":1,"baseline_sha":"bfc0a75","runs":[]}',
                encoding="utf-8",
            )
            (out / "gate-result.json").write_text(
                '{"status":"pass","regression_pct":-2.5,"checks":[]}',
                encoding="utf-8",
            )

            cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                os.environ["GITHUB_RUN_NUMBER"] = "247"
                os.environ["RUNNER_RAM_GB"] = "7"
                os.environ["K6_VERSION"] = "0.53.0"
                build_benchmark_data.OUT_DIR = out
                build_benchmark_data.BASELINE_PATH = data_schema / "baseline.json"
                build_benchmark_data.main()
                data = json.loads((out / "benchmark-data.json").read_text(encoding="utf-8"))
                run = data["runs"][0]
                self.assertEqual(run["run_number"], 247)
                self.assertEqual(run["runner_ram_gb"], 7)
                self.assertEqual(run["k6_version"], "0.53.0")
                go = run["go_benchmarks"].get("BenchmarkProxyOverhead", {})
                self.assertEqual(go["samples"], 5)
                self.assertAlmostEqual(go["ci_95_low"], 8200000.0)
                self.assertAlmostEqual(go["ci_95_high"], 8800000.0)
                self.assertIn("metric_deltas", run)
            finally:
                os.chdir(cwd)

    def test_build_benchmark_data_writes_schema_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "benchmarks" / "output"
            data_schema = root / "benchmarks" / "data-schema"
            out.mkdir(parents=True)
            data_schema.mkdir(parents=True)
            shutil.copy(TESTDATA / "latest-pass.json", out / "latest.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", data_schema / "baseline.json")
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", out / "baseline.json")
            (out / "prev-benchmark-data.json").write_text(
                '{"schema_version":1,"baseline_sha":"bfc0a75","runs":[]}',
                encoding="utf-8",
            )
            (out / "gate-result.json").write_text(
                '{"status":"pass","regression_pct":-2.5,"checks":[]}',
                encoding="utf-8",
            )

            cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                build_benchmark_data.OUT_DIR = out
                build_benchmark_data.BASELINE_PATH = data_schema / "baseline.json"
                build_benchmark_data.main()
                target = out / "benchmark-data.json"
                self.assertTrue(target.exists(), target)
                data = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(data["schema_version"], 1)
                self.assertEqual(data["baseline_sha"], "bfc0a75")
                self.assertEqual(len(data["runs"]), 1)
                self.assertEqual(data["runs"][0]["status"], "pass")
            finally:
                os.chdir(cwd)

    def test_generate_badge_writes_svg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "benchmark-data.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "baseline_sha": "bfc0a75",
                        "runs": [{"status": "pass", "k6": {"p99_ms": 4.5}}],
                    }
                ),
                encoding="utf-8",
            )
            generate_badge.OUT_DIR = out
            generate_badge.main()
            badge = out / "badge.svg"
            self.assertTrue(badge.exists())
            self.assertIn("pass", badge.read_text(encoding="utf-8").lower())


class ValidatePublishedDataTests(unittest.TestCase):
    def test_validate_published_data_accepts_seed_file(self) -> None:
        seed = ROOT / "docs/app/public/benchmarks/benchmark-data.json"
        if not seed.exists():
            self.skipTest("published benchmark seed not available")
        validate_published_data.validate_payload(
            json.loads(seed.read_text(encoding="utf-8"))
        )

    def test_validate_published_data_rejects_path_traversal(self) -> None:
        with self.assertRaises(SystemExit):
            validate_published_data.resolve_benchmark_data_path("../../etc/passwd")

    def test_compare_pr_benchmark_json_accepts_matching_payloads(self) -> None:
        compare = load_module("compare_pr_benchmark_json", SCRIPTS / "compare_pr_benchmark_json.py")
        seed = ROOT / "docs/app/public/benchmarks/benchmark-data.json"
        if not seed.exists():
            self.skipTest("published benchmark seed not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            committed = root / "docs/app/public/benchmarks"
            artifact = root / "benchmarks/output"
            committed.mkdir(parents=True)
            artifact.mkdir(parents=True)
            shutil.copy(seed, committed / "benchmark-data.json")
            shutil.copy(seed, artifact / "benchmark-data.json")
            cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                self.assertEqual(compare.main(), 0)
            finally:
                os.chdir(cwd)

    def test_resolve_output_baseline_sha_inherits_from_prev_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "benchmarks" / "output"
            data_schema = Path(tmp) / "benchmarks" / "data-schema"
            out.mkdir(parents=True)
            data_schema.mkdir(parents=True)
            shutil.copy(TESTDATA / "latest-pass.json", out / "latest.json")
            (data_schema / "baseline.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "baseline": {
                            "target_commit": "unset",
                            "baseline_sha": "unset",
                            "proxy_overhead_p99_ms": 20.0,
                            "throughput_rps": 0.0,
                            "allocs_per_op": 0.0,
                            "bytes_per_op": 0.0,
                        },
                        "policy": {
                            "max_regression_pct": 20.0,
                            "max_proxy_overhead_p99_ms": 20.0,
                            "max_error_rate": 0.001,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (out / "prev-benchmark-data.json").write_text(
                '{"schema_version":1,"baseline_sha":"bfc0a75","runs":[]}',
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                import os

                os.chdir(tmp)
                build_benchmark_data.OUT_DIR = out
                build_benchmark_data.BASELINE_PATH = data_schema / "baseline.json"
                latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
                resolved = build_benchmark_data.resolve_output_baseline_sha(latest, [])
                self.assertEqual(resolved, "bfc0a75")
            finally:
                os.chdir(cwd)

    def test_validate_published_data_rejects_invalid_payloads(self) -> None:
        for name, payload in _invalid_payload_cases():
            with self.subTest(name=name):
                _assert_validate_rejects(payload)

    def test_validate_published_data_rejects_duplicate_pr_number(self) -> None:
        payload = {
            "schema_version": 1,
            "baseline_sha": "bfc0a75",
            "runs": [
                {
                    "sha": "a" * 40,
                    "short_sha": "aaaaaaa",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "branch": "main",
                    "pr_number": 1,
                    "status": "pass",
                    "k6": {"p99_ms": 4.0, "error_rate": 0.0},
                },
                {
                    "sha": "b" * 40,
                    "short_sha": "bbbbbbb",
                    "timestamp": "2026-01-02T00:00:00+00:00",
                    "branch": "main",
                    "pr_number": 1,
                    "status": "pass",
                    "k6": {"p99_ms": 4.0, "error_rate": 0.0},
                },
            ],
        }
        _assert_validate_rejects(payload)


if __name__ == "__main__":
    sys.exit(unittest.main())
