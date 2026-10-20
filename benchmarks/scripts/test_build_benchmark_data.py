#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark_test_support import ROOT, SCRIPTS, TESTDATA, load_module

build_benchmark_data = load_module("build_benchmark_data", SCRIPTS / "build_benchmark_data.py")
generate_badge = load_module("generate_badge", SCRIPTS / "generate_badge.py")


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
                os.chdir(root)
                build_benchmark_data.OUT_DIR = out
                build_benchmark_data.BASELINE_PATH = data_schema / "baseline.json"
                build_benchmark_data.main()
                target = out / "benchmark-data.json"
                self.assertTrue(target.exists(), target)
                data = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(data["schema_version"], 1)
                pinned = json.loads((data_schema / "baseline.json").read_text(encoding="utf-8"))
                want_sha = pinned["baseline"]["baseline_sha"]
                self.assertEqual(data["baseline_sha"], want_sha)
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


if __name__ == "__main__":
    unittest.main()
