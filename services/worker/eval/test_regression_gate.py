"""CI-enforcement tests: regression_gate must exit non-zero on >3pp drop."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import regression_gate as gate_mod

_DIR = Path(__file__).resolve().parent


def _baseline(*, precision_factual: float = 1.0) -> dict:
    metrics = {
        "precision_factual": precision_factual,
        "recall_factual": 1.0,
        "precision_procedural": 1.0,
        "recall_procedural": 1.0,
        "precision_preference": 1.0,
        "recall_preference": 1.0,
        "precision_behavioral": 1.0,
        "recall_behavioral": 1.0,
        "precision_episodic": 1.0,
        "recall_episodic": 1.0,
        "precision_macro": 1.0,
        "recall_macro": 1.0,
        "category_assignment_accuracy": 1.0,
        "temporal_field_accuracy": 1.0,
    }
    return {
        "schema_version": 1,
        "gold_set": "v1",
        "policy": {"max_regression_pp": 3.0},
        "providers": {
            "openai": {
                "model": "gpt-4o-mini",
                "enforcement": "ci",
                "source": "cassette",
                "last_refreshed": "2026-09-03",
                "metrics": metrics,
            },
            "vllm": {
                "model": "Qwen2.5-14B-Instruct",
                "enforcement": "manual",
                "source": "manual_runbook",
                "last_refreshed": None,
                "metrics": {k: None for k in metrics},
            },
        },
    }


def _latest(*, precision_factual: float) -> dict:
    metrics = _baseline()["providers"]["openai"]["metrics"].copy()
    metrics["precision_factual"] = precision_factual
    return {
        "benchmark": "extraction_quality",
        "provider": "openai",
        "enforcement": "ci",
        "metrics": metrics,
    }


def _write_gate_inputs(
    out: Path, *, latest: dict, baseline: dict
) -> tuple[Path, Path, Path]:
    latest_path = out / "latest.json"
    baseline_path = out / "baseline_results.json"
    gate_path = out / "gate-result.json"
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    gate_mod.LATEST_PATH = latest_path
    gate_mod.BASELINE_PATH = baseline_path
    gate_mod.GATE_RESULT_PATH = gate_path
    return latest_path, baseline_path, gate_path


class ExtractionRegressionGateTests(unittest.TestCase):
    def test_main_exits_zero_within_three_pp(self) -> None:
        """0.98 is a 2pp drop from 1.0 — within 3pp policy."""
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            _write_gate_inputs(
                Path(tmp),
                latest=_latest(precision_factual=0.98),
                baseline=_baseline(),
            )
            self.assertEqual(gate_mod.main(), 0)
            result = json.loads(gate_mod.GATE_RESULT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "pass")

    def test_main_exits_zero_at_exact_three_pp_boundary(self) -> None:
        """0.97 is exactly 3pp from 1.0 — inclusive boundary must pass."""
        drop = gate_mod._pp_drop(0.97, 1.0)
        self.assertTrue(gate_mod._within_max_pp(drop, 3.0))
        self.assertAlmostEqual(drop, 3.0, places=9)
        ok, checks, _ = gate_mod.evaluate_gate(
            _latest(precision_factual=0.97),
            _baseline(),
        )
        self.assertTrue(ok)
        self.assertTrue(all(c["ok"] for c in checks))

    def test_main_exits_nonzero_when_metric_regresses_beyond_three_pp(self) -> None:
        """0.96 is a 4pp drop from 1.0 — must fail the build (not warn-only)."""
        with tempfile.TemporaryDirectory(dir=_DIR) as tmp:
            _write_gate_inputs(
                Path(tmp),
                latest=_latest(precision_factual=0.96),
                baseline=_baseline(),
            )
            self.assertEqual(gate_mod.main(), 1)
            result = json.loads(gate_mod.GATE_RESULT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "fail")
            failed = [c["name"] for c in result["checks"] if not c["ok"]]
            self.assertTrue(any("precision_factual" in name for name in failed))

    def test_manual_vllm_block_does_not_fail_gate(self) -> None:
        ok, checks, _summary = gate_mod.evaluate_gate(
            _latest(precision_factual=1.0),
            _baseline(),
        )
        self.assertTrue(ok)
        self.assertTrue(all("vllm" not in c["name"] for c in checks))

    def test_parse_float_rejects_nan_inf_and_garbage(self) -> None:
        self.assertIsNone(gate_mod._parse_float(None))
        self.assertIsNone(gate_mod._parse_float("nope"))
        self.assertIsNone(gate_mod._parse_float(float("nan")))
        self.assertIsNone(gate_mod._parse_float(float("inf")))
        self.assertIsNone(gate_mod._parse_float("-inf"))
        self.assertEqual(gate_mod._parse_float("1.5"), 1.5)

    def test_max_regression_pp_inf_rejected(self) -> None:
        baseline = _baseline()
        baseline["policy"] = {"max_regression_pp": "inf"}
        ok, checks, lines = gate_mod.evaluate_gate(_latest(precision_factual=1.0), baseline)
        self.assertFalse(ok)
        self.assertEqual(checks, [])
        self.assertTrue(any("max_regression_pp" in line for line in lines))

        baseline2 = _baseline()
        baseline2["policy"] = {"max_regression_pp": float("inf")}
        ok2, _, lines2 = gate_mod.evaluate_gate(_latest(precision_factual=1.0), baseline2)
        self.assertFalse(ok2)
        self.assertTrue(any("max_regression_pp" in line for line in lines2))

    def test_missing_baseline_gated_metric_fails(self) -> None:
        baseline = _baseline()
        del baseline["providers"]["openai"]["metrics"]["temporal_field_accuracy"]
        ok, checks, summary = gate_mod.evaluate_gate(_latest(precision_factual=1.0), baseline)
        self.assertFalse(ok)
        self.assertTrue(any("temporal_field_accuracy" in c["name"] for c in checks))
        self.assertTrue(any("missing from baseline" in line for line in summary))

    def test_evaluate_gate_rejects_bad_shapes_and_missing_metrics(self) -> None:
        ok, _checks, lines = gate_mod.evaluate_gate({"metrics": {}}, {"providers": []})
        self.assertFalse(ok)
        self.assertTrue(any("no CI-enforced" in line for line in lines))

        ok2, checks2, _lines2 = gate_mod.evaluate_gate(
            {"provider": "openai", "metrics": []},
            _baseline(),
        )
        self.assertFalse(ok2)
        self.assertTrue(checks2 == [] or any(not c["ok"] for c in checks2))

        baseline = _baseline()
        baseline["policy"] = {}
        baseline["providers"]["openai"]["metrics"] = "nope"
        ok3, checks3, _ = gate_mod.evaluate_gate(_latest(precision_factual=1.0), baseline)
        self.assertFalse(ok3)
        self.assertTrue(any(not c["ok"] for c in checks3))

        baseline2 = _baseline()
        latest = _latest(precision_factual=1.0)
        latest["metrics"] = {k: None for k in latest["metrics"]}
        ok4, checks4, _ = gate_mod.evaluate_gate(latest, baseline2)
        self.assertFalse(ok4)
        self.assertTrue(any(not c["ok"] for c in checks4))

        ok5, _c5, lines5 = gate_mod.evaluate_gate(
            {"provider": "openai", "metrics": {"precision_factual": 1.0}},
            {"policy": {"max_regression_pp": 3.0}, "providers": "bad"},
        )
        self.assertFalse(ok5)
        self.assertTrue(any("providers" in line for line in lines5))

    def test_no_ci_checks_when_provider_mismatches(self) -> None:
        latest = _latest(precision_factual=1.0)
        latest["provider"] = "other"
        ok, checks, summary = gate_mod.evaluate_gate(latest, _baseline())
        self.assertFalse(ok)
        self.assertEqual(checks, [])
        self.assertTrue(any("no CI-enforced" in line for line in summary))


if __name__ == "__main__":
    unittest.main()
