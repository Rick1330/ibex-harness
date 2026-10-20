#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "benchmarks" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import go_bench_gate


class GoBenchGateTests(unittest.TestCase):
    def _write_output(self, path: Path, ns_values: dict[str, list[float]]) -> None:
        lines: list[str] = []
        for name, values in ns_values.items():
            for value in values:
                lines.append(
                    f"{name}-8\t1000\t{value:.0f} ns/op\t200 B/op\t20 allocs/op"
                )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_parse_benchmark_line_extracts_metrics_and_strips_cpu_suffix(self) -> None:
        sample = go_bench_gate.parse_benchmark_line(
            "BenchmarkProxyOverhead-22\t1000\t611839 ns/op\t198194 B/op\t856 allocs/op"
        )
        if sample is None:
            self.fail("expected a parsed benchmark sample")
        self.assertEqual(sample.name, "BenchmarkProxyOverhead")
        self.assertAlmostEqual(sample.ns_per_op, 611839.0)
        self.assertAlmostEqual(sample.bytes_per_op, 198194.0)
        self.assertAlmostEqual(sample.allocs_per_op, 856.0)

    def test_parse_benchmark_line_ignores_non_benchmark_output(self) -> None:
        self.assertIsNone(go_bench_gate.parse_benchmark_line("PASS"))
        self.assertIsNone(go_bench_gate.parse_benchmark_line("ok  \tibex/benchmarks"))

    def test_parse_benchmark_line_rejects_malformed_metrics(self) -> None:
        with self.assertRaises(go_bench_gate.GateInputError):
            go_bench_gate.parse_benchmark_line("BenchmarkProxyOverhead-8 1000 100 ns/op")
        with self.assertRaises(go_bench_gate.GateInputError):
            go_bench_gate.parse_benchmark_line(
                "BenchmarkProxyOverhead-8 1000 100 ns/op\t200 B/op"
            )

    def test_parse_benchmark_line_rejects_negative_and_non_finite_metrics(self) -> None:
        for metric in ("-1", "nan", "inf"):
            with self.assertRaises(go_bench_gate.GateInputError):
                go_bench_gate.parse_benchmark_line(
                    f"BenchmarkProxyOverhead-8 1000 {metric} ns/op\t200 B/op\t20 allocs/op"
                )
        with self.assertRaises(go_bench_gate.GateInputError):
            go_bench_gate.parse_benchmark_line(
                "BenchmarkProxyOverhead-8 1000 100 ns/op\t-1 B/op\t20 allocs/op"
            )

    def test_summarize_uses_median_across_samples(self) -> None:
        samples = [
            go_bench_gate.BenchSample("BenchmarkProxyOverhead", value, 200.0, 20.0)
            for value in (100.0, 900.0, 200.0, 300.0, 400.0)
        ]
        summary = go_bench_gate.summarize(samples)
        self.assertEqual(summary.samples, 5)
        self.assertAlmostEqual(summary.ns_per_op, 300.0)

    def test_build_checks_passes_within_tolerance(self) -> None:
        base = {
            name: go_bench_gate.BenchSummary(5, 1000.0, 200.0, 20.0)
            for name in go_bench_gate.DEFAULT_BENCHMARKS
        }
        head = {
            name: go_bench_gate.BenchSummary(5, 1199.0, 200.0, 20.0)
            for name in go_bench_gate.DEFAULT_BENCHMARKS
        }
        checks = go_bench_gate.build_checks(base, head, go_bench_gate.DEFAULT_BENCHMARKS, 20.0)
        self.assertTrue(all(check.passed for check in checks))

    def test_build_checks_fails_on_latency_regression(self) -> None:
        base = {
            name: go_bench_gate.BenchSummary(5, 1000.0, 200.0, 20.0)
            for name in go_bench_gate.DEFAULT_BENCHMARKS
        }
        head = {
            name: go_bench_gate.BenchSummary(5, 1300.0, 200.0, 20.0)
            for name in go_bench_gate.DEFAULT_BENCHMARKS
        }
        checks = go_bench_gate.build_checks(base, head, go_bench_gate.DEFAULT_BENCHMARKS, 20.0)
        failed = [check for check in checks if not check.passed]
        self.assertEqual([check.metric for check in failed], ["ns_per_op", "ns_per_op"])
        self.assertEqual(
            {check.benchmark for check in failed},
            set(go_bench_gate.DEFAULT_BENCHMARKS),
        )

    def test_zero_base_reports_infinite_change_and_fails(self) -> None:
        base = {
            "BenchmarkProxyOverhead": go_bench_gate.BenchSummary(5, 0.0, 0.0, 0.0),
        }
        head = {
            "BenchmarkProxyOverhead": go_bench_gate.BenchSummary(5, 100.0, 0.0, 0.0),
        }
        checks = go_bench_gate.build_checks(
            base, head, ["BenchmarkProxyOverhead"], 20.0
        )
        self.assertEqual(
            [check.metric for check in checks if not check.passed], ["ns_per_op"]
        )
        self.assertTrue(math.isinf(checks[0].change_pct))

    def test_build_checks_fails_when_missing_benchmark(self) -> None:
        base = {
            "BenchmarkProxyOverhead": go_bench_gate.BenchSummary(5, 1000.0, 200.0, 20.0),
        }
        head = {
            "BenchmarkProxyOverhead": go_bench_gate.BenchSummary(5, 1000.0, 200.0, 20.0),
        }
        with self.assertRaises(go_bench_gate.GateInputError):
            go_bench_gate.build_checks(base, head, go_bench_gate.DEFAULT_BENCHMARKS, 20.0)

    def test_main_writes_failure_result_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_path = root / "base.txt"
            head_path = root / "head.txt"
            result_path = root / "result.json"
            self._write_output(
                base_path,
                {
                    "BenchmarkProxyOverhead": [1000.0, 1000.0],
                    "BenchmarkProxyChatOverhead": [1000.0, 1000.0],
                },
            )
            self._write_output(
                head_path,
                {
                    "BenchmarkProxyOverhead": [1500.0, 1500.0],
                    "BenchmarkProxyChatOverhead": [1000.0, 1000.0],
                },
            )
            self.assertEqual(
                go_bench_gate.main(
                    [
                        "--base",
                        str(base_path),
                        "--head",
                        str(head_path),
                        "--output",
                        str(result_path),
                        "--base-ref",
                        "origin/main",
                    ]
                ),
                1,
            )
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["base_ref"], "origin/main")
            failed = [row for row in payload["checks"] if not row["ok"]]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["metric"], "ns_per_op")

    def test_main_returns_input_error_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head_path = root / "head.txt"
            self._write_output(
                head_path,
                {
                    "BenchmarkProxyOverhead": [1000.0],
                    "BenchmarkProxyChatOverhead": [1000.0],
                },
            )
            self.assertEqual(
                go_bench_gate.main(
                    [
                        "--base",
                        str(root / "missing.txt"),
                        "--head",
                        str(head_path),
                    ]
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
