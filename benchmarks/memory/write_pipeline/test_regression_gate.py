"""Synthetic failure-path tests for write-pipeline regression_gate.main()."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_BENCH_MEMORY = _DIR.parent
_SPEC = importlib.util.spec_from_file_location(
    "write_regression_gate",
    _DIR / "regression_gate.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load write regression_gate")
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))
gate_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["write_regression_gate"] = gate_mod
_SPEC.loader.exec_module(gate_mod)


def _latest(*, p95: float) -> dict:
    return {
        "benchmark": "write_pipeline",
        "iterations": 40,
        "metrics": {
            "latency_ms_p50": p95 * 0.8,
            "latency_ms_p95": p95,
            "latency_ms_p99": p95 * 1.1,
        },
    }


class WriteRegressionGateMainTests(unittest.TestCase):
    def test_main_exits_zero_within_sla_and_regression_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest.json").write_text(json.dumps(_latest(p95=150.0)), encoding="utf-8")
            (out / "baseline.json").write_text(
                (_DIR / "baseline.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            gate_mod.LATEST_PATH = out / "latest.json"
            gate_mod.BASELINE_PATH = out / "baseline.json"
            gate_mod.GATE_RESULT_PATH = out / "gate-result.json"
            self.assertEqual(gate_mod.main(), 0)
            result = json.loads(gate_mod.GATE_RESULT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "pass")

    def test_main_exits_nonzero_when_p95_exceeds_sla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest.json").write_text(json.dumps(_latest(p95=250.0)), encoding="utf-8")
            (out / "baseline.json").write_text(
                (_DIR / "baseline.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            gate_mod.LATEST_PATH = out / "latest.json"
            gate_mod.BASELINE_PATH = out / "baseline.json"
            gate_mod.GATE_RESULT_PATH = out / "gate-result.json"
            self.assertEqual(gate_mod.main(), 1)
            result = json.loads(gate_mod.GATE_RESULT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "fail")
            failed = [c["name"] for c in result["checks"] if not c["ok"]]
            self.assertIn("p95 SLA (ms)", failed)

    def test_main_exits_nonzero_on_baseline_regression_beyond_policy(self) -> None:
        """p95=240 is ~20.6% above baseline 199 — exceeds max_regression_pct=20."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest.json").write_text(json.dumps(_latest(p95=240.0)), encoding="utf-8")
            (out / "baseline.json").write_text(
                (_DIR / "baseline.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            gate_mod.LATEST_PATH = out / "latest.json"
            gate_mod.BASELINE_PATH = out / "baseline.json"
            gate_mod.GATE_RESULT_PATH = out / "gate-result.json"
            self.assertEqual(gate_mod.main(), 1)
            result = json.loads(gate_mod.GATE_RESULT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "fail")


if __name__ == "__main__":
    unittest.main()
