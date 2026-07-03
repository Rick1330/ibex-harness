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
                '{"schema_version":1,"baseline_sha":"","runs":[]}',
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
                '{"schema_version":1,"baseline_sha":"","runs":[]}',
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
                        "baseline_sha": "",
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


if __name__ == "__main__":
    sys.exit(unittest.main())
