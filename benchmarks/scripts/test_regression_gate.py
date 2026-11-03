#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark_test_support import ROOT, SCRIPTS, TESTDATA, load_module

regression_gate = load_module("regression_gate", SCRIPTS / "regression_gate.py")


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
        names = {name for name, _, _, _ in checks}
        self.assertIn("stage rate_limit present", names)
        self.assertIn("stage rate_limit regression (%)", names)
        self.assertNotIn("regression vs baseline (%)", names)

    def test_build_checks_fails_on_high_p99_and_error_rate(self) -> None:
        latest = regression_gate.normalize_latest(json.loads((TESTDATA / "latest-fail.json").read_text()))
        baseline = regression_gate.normalize_baseline(
            json.loads((ROOT / "benchmarks/data-schema/baseline.json").read_text())
        )
        checks = regression_gate.build_checks(latest, baseline)
        failed = [name for name, _, _, passed in checks if not passed]
        self.assertIn("k6 p99 SLA", failed)
        self.assertIn("error rate", failed)

    def test_build_checks_fails_on_rate_limit_regression(self) -> None:
        latest = regression_gate.normalize_latest(
            {
                "k6": {
                    "p99_ms": 12.0,
                    "req_per_s": 850.5,
                    "error_rate": 0.0,
                    "check_rate": 1.0,
                },
                "go_benchmarks": {"BenchmarkProxyOverhead": {"allocs_per_op": 8.0, "bytes_per_op": 512.0}},
                "stages": {"synthetic_total_us": 8500.0, "synthetic_rate_limit_us": 400.0},
            }
        )
        baseline = regression_gate.normalize_baseline(
            json.loads((ROOT / "benchmarks/data-schema/baseline.json").read_text())
        )
        checks = regression_gate.build_checks(latest, baseline)
        failed = [name for name, _, _, passed in checks if not passed]
        self.assertIn("stage rate_limit regression (%)", failed)

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


if __name__ == "__main__":
    unittest.main()
