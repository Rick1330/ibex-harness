"""Unit tests for shared regression gate helpers."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "regression_gate_common",
    Path(__file__).resolve().parent / "regression_gate_common.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load regression_gate_common")
gate = importlib.util.module_from_spec(_SPEC)
sys.modules["regression_gate_common"] = gate
_SPEC.loader.exec_module(gate)


class RegressionGateCommonTests(unittest.TestCase):
    def test_higher_is_better_passes_small_drop(self) -> None:
        checks = gate.build_metric_checks(
            {"precision_at_5": 0.97},
            {"precision_at_5": 1.0},
            max_regression_pct=5.0,
            higher_is_better=True,
        )
        self.assertTrue(all(passed for *_, passed in checks))

    def test_higher_is_better_fails_large_drop(self) -> None:
        checks = gate.build_metric_checks(
            {"precision_at_5": 0.90},
            {"precision_at_5": 1.0},
            max_regression_pct=5.0,
            higher_is_better=True,
        )
        self.assertFalse(all(passed for *_, passed in checks))

    def test_lower_is_better_fails_latency_regression(self) -> None:
        checks = gate.build_metric_checks(
            {"latency_ms_p95": 250.0},
            {"latency_ms_p95": 100.0},
            max_regression_pct=20.0,
            higher_is_better=False,
        )
        self.assertFalse(all(passed for *_, passed in checks))


if __name__ == "__main__":
    unittest.main()
