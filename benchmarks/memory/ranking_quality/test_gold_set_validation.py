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

    def test_invalid_memory_row_skips_catalog_updates(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        bad_key = payload["memories"][0]["content_key"]
        payload["memories"][0] = {**payload["memories"][0], "category": "not-a-category"}
        payload["queries"][0]["expected_content_keys"] = [bad_key]
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("invalid category" in e for e in errors))
        self.assertTrue(
            any("references unknown content_key" in e for e in errors),
            "invalid memory must not be indexed for query lookups",
        )

    def test_unknown_first_expected_key_reports_error(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["queries"][0]["expected_content_keys"] = ["missing-content-key"]
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(
            any("unknown first expected content_key" in e for e in errors),
            "\n".join(errors),
        )

    def test_rejects_fractional_age(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["memories"][0] = {**payload["memories"][0], "valid_from_days_ago": 3.5}
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("must be an integer" in e for e in errors))

    def test_rejects_bool_hotspot(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["memories"][0] = {**payload["memories"][0], "embedding_hotspot": True}
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("must be an integer" in e for e in errors))

    def test_rejects_non_string_category(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["memories"][0] = {**payload["memories"][0], "category": 42}
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("category must be a string" in e for e in errors))

    def test_rejects_non_string_expected_key(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["queries"][0]["expected_content_keys"] = [123]
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("expected_content_keys items must be strings" in e for e in errors))

    def test_rejects_empty_query_id(self) -> None:
        payload = json.loads((_DIR / "gold_set_v1.json").read_text(encoding="utf-8"))
        payload["queries"][0]["query_id"] = ""
        errors = validate_mod.validate_gold_set(payload)
        self.assertTrue(any("query_id must be non-empty" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
