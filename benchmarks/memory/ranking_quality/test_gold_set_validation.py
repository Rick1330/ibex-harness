"""Unit tests for gold_set_v1.json validation."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    memory_dir = _DIR.parents[2] / "services" / "memory"
    if str(memory_dir) not in sys.path:
        sys.path.insert(0, str(memory_dir))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


validate_mod = _load_module("validate_gold_set", _DIR / "validate_gold_set.py")


class GoldSetValidationTests(unittest.TestCase):
    def test_committed_gold_set_passes(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        errors = validate_mod.validate_gold_set(payload)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_rejects_placeholder_content(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["memories"][0] = {
            **payload["memories"][0],
            "content": "gold ranking placeholder",
        }
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("placeholder" in e for e in errors))

    def test_rejects_missing_decay_query(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["queries"] = [
            q for q in payload["queries"] if q["query_id"] != "q_pref_theme_decay"
        ]
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("decay" in e for e in errors))

    def test_rejects_missing_confidence(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        row = dict(payload["memories"][0])
        del row["confidence"]
        payload["memories"][0] = row
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("missing confidence" in e for e in errors))

    def test_rejects_invalid_confidence(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["memories"][0] = {**payload["memories"][0], "confidence": 1.5}
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("confidence must be in [0, 1]" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
