#!/usr/bin/env python3
from __future__ import annotations

import unittest

from benchmark_test_support import ROOT, SCRIPTS, TESTDATA, load_module

aggregate_metrics = load_module("aggregate_metrics", SCRIPTS / "aggregate_metrics.py")


class AggregateMetricsTests(unittest.TestCase):
    def test_parse_go_bench_line_extracts_metrics(self) -> None:
        line = "BenchmarkProxyOverhead-8   	  200000	      8500 ns/op	     512 B/op	       8 allocs/op"
        row = aggregate_metrics.parse_go_bench_line(line)
        if row is None:
            self.fail("expected a parsed Go benchmark line")
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


if __name__ == "__main__":
    unittest.main()
