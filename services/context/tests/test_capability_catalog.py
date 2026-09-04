"""Capability catalog loader tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
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
        catalog = default_catalog()
        with self.assertRaises(UnknownModelError):
            catalog.for_model("missing-model")

    def test_load_rejects_bad_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 99,
                        "models": [],
                        "tokenizer_families": {},
                        "source": "x",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_catalog(path)

    def test_catalog_available_from_installed_wheel(self) -> None:
        """Package data must ship in the wheel and load via default_catalog()."""
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            built = subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", str(dist), str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(built.returncode, 0, built.stderr or built.stdout)
            wheels = list(dist.glob("ibex_context-*.whl"))
            self.assertEqual(len(wheels), 1, wheels)
            with zipfile.ZipFile(wheels[0]) as zf:
                names = zf.namelist()
            self.assertIn(
                "app/data/model_capabilities.v1.json",
                names,
                f"catalog missing from wheel; members={names}",
            )
            site = Path(tmp) / "site"
            site.mkdir()
            installed = subprocess.run(
                ["uv", "pip", "install", "--no-deps", "--python", sys.executable, "--target", str(site), str(wheels[0])],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr or installed.stdout)
            catalog_path = site / "app" / "data" / "model_capabilities.v1.json"
            self.assertTrue(catalog_path.is_file(), catalog_path)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(site)
            probe = (
                "from app.capability_catalog import default_catalog; "
                "c = default_catalog(); "
                "assert 'gpt-4o' in c.models"
            )
            probed = subprocess.run(
                [sys.executable, "-c", probe],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(probed.returncode, 0, probed.stderr or probed.stdout)


if __name__ == "__main__":
    unittest.main()
