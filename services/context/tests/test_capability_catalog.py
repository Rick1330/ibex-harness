"""Capability catalog loader tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.capability_catalog import UnknownModelError, default_catalog, load_catalog


class CapabilityCatalogTests(unittest.TestCase):
    def test_default_catalog_includes_builtins(self) -> None:
        catalog = default_catalog()
        self.assertEqual(catalog.schema_version, 1)
        self.assertIn("gpt-4o", catalog.models)
        self.assertIn("claude-sonnet-4-5", catalog.models)
        self.assertEqual(catalog.for_model("gpt-4o").tokenizer_family, "o200k_base")

    def test_for_model_unknown(self) -> None:
        with self.assertRaises(UnknownModelError):
            default_catalog().for_model("missing-model")

    def test_load_rejects_bad_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"schema_version": 99, "models": [], "tokenizer_families": {}, "source": "x"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(path)


if __name__ == "__main__":
    unittest.main()
