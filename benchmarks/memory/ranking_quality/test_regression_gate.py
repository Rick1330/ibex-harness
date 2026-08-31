"""Synthetic failure-path tests for ranking-quality regression_gate.main()."""

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
    "ranking_regression_gate",
    _DIR / "regression_gate.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load ranking regression_gate")
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))
gate_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["ranking_regression_gate"] = gate_mod
_SPEC.loader.exec_module(gate_mod)


def _latest(*, precision_at_5: float) -> dict:
    return {
        "benchmark": "ranking_quality",
        "metrics": {
            "precision_at_5": precision_at_5,
            "recall_at_10": 1.0,
            "mrr": 1.0,
            "top_category_accuracy": 1.0,
        },
    }


class RankingRegressionGateMainTests(unittest.TestCase):
    def test_main_exits_zero_within_regression_tolerance(self) -> None:
        """0.98 precision@5 is a 2% drop from baseline 1.0 — within 5% policy."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest.json").write_text(
                json.dumps(_latest(precision_at_5=0.98)),
                encoding="utf-8",
            )
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

    def test_main_exits_nonzero_when_precision_regresses_beyond_policy(self) -> None:
        """0.94 precision@5 is a 6% drop — exceeds max_regression_pct=5."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest.json").write_text(
                json.dumps(_latest(precision_at_5=0.94)),
                encoding="utf-8",
            )
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
            self.assertTrue(any("precision_at_5" in name for name in failed))


if __name__ == "__main__":
    unittest.main()
