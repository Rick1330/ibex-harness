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
    spec.loader.exec_module(module)
    return module


aggregate_metrics = load_module("aggregate_metrics", SCRIPTS / "aggregate_metrics.py")
regression_gate = load_module("regression_gate", SCRIPTS / "regression_gate.py")
build_site = load_module("build_site", SCRIPTS / "build_site.py")


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

    def test_safe_int_rejects_invalid_runner_vcpu(self) -> None:
        self.assertEqual(aggregate_metrics.safe_int("not-a-number", 4), 4)

    def test_stage_breakdown_maps_go_bench_to_ms(self) -> None:
        go_bench = aggregate_metrics.parse_go_bench(TESTDATA / "go-bench-sample.txt")
        stages = aggregate_metrics.stage_breakdown(go_bench)
        self.assertGreater(stages["total_overhead_p99_ms"], 0.0)
        self.assertGreater(stages["auth_lru_p99_ms"], 0.0)


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


class BuildSiteTests(unittest.TestCase):
    def test_build_site_requires_dashboard_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "benchmarks" / "output"
            site_src = root / "benchmarks" / "site"
            data_schema = root / "benchmarks" / "data-schema"
            site_src.mkdir(parents=True)
            data_schema.mkdir(parents=True)
            shutil.copytree(ROOT / "benchmarks/site", site_src, dirs_exist_ok=True)
            shutil.copy(ROOT / "benchmarks/data-schema/baseline.json", data_schema / "baseline.json")
            out.mkdir(parents=True)
            (out / "runs.json").write_text('{"runs":[]}', encoding="utf-8")

            cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                build_site.main()
                required = [
                    out / "site/index.html",
                    out / "site/data/runs.json",
                    out / "site/data/baseline.json",
                    out / "site/data/metadata.json",
                ]
                for path in required:
                    self.assertTrue(path.exists(), path)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    sys.exit(unittest.main())
