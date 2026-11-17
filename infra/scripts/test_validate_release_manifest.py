#!/usr/bin/env python3
"""Tests for infra/scripts/validate-release-manifest.py.

The validator is the last check before ``release-manifest.json`` is uploaded to
a GitHub release, so every case here is a manifest that must not reach a
published release: a document that is not JSON, a schema violation, a timestamp
that is not RFC 3339, and a path that resolves outside the checkout.

``REPO_ROOT`` is redirected to a scratch tree, so a case about containment does
not have to write anything into the working tree to be outside the checkout.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("validate-release-manifest.py")
SPEC = importlib.util.spec_from_file_location("validate_release_manifest", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load validate-release-manifest.py")
validate_release_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_release_manifest
SPEC.loader.exec_module(validate_release_manifest)

SCHEMA = Path(__file__).resolve().parents[1] / "release-manifest.schema.json"
DIGEST = "sha256:" + "a" * 64
HASH = "b" * 64
COMMIT = "c" * 40


def conforming_manifest() -> dict[str, object]:
    """A manifest that satisfies every constraint in the published schema."""
    return {
        "manifest_version": 1,
        "tag": "v1.2.3",
        "platform_version": "1.2.3",
        "generated_at": "2026-11-01T00:00:00Z",
        "source": {"repository": "Rick1330/ibex-harness", "commit": COMMIT},
        "images": {"auth": DIGEST},
        "contracts": {"openapi_sha256": HASH, "proto_sha256": HASH},
        "migrations": {"postgres": 2, "clickhouse": 1},
        "bundles": [],
    }


class ValidateReleaseManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        # The real schema, copied inside the scratch checkout so the cases run
        # against the published contract rather than a fixture copy of it.
        self.schema = self.checkout / SCHEMA.name
        self.schema.write_text(SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")

    def write(self, text: str) -> Path:
        path = self.checkout / "release-manifest.json"
        path.write_text(text, encoding="utf-8")
        return path

    def run_validator(self, path: Path, schema: Path | None = None) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(validate_release_manifest, "REPO_ROOT", self.checkout),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = validate_release_manifest.main(
                [str(path), "--schema", str(schema or self.schema)]
            )
        return code, out.getvalue() + err.getvalue()

    def test_a_conforming_manifest_exits_zero(self) -> None:
        code, output = self.run_validator(self.write(json.dumps(conforming_manifest())))
        self.assertEqual(code, 0, output)
        self.assertIn("conforms to", output)

    def test_invalid_json_exits_one(self) -> None:
        code, output = self.run_validator(self.write('{"manifest_version": 1,'))
        self.assertEqual(code, 1, output)
        self.assertIn("is not valid JSON", output)

    def test_a_schema_violation_exits_one_naming_the_json_path(self) -> None:
        missing_migrations = conforming_manifest()
        missing_migrations.pop("migrations")
        bad_digest = conforming_manifest()
        bad_digest["images"] = {"auth": "sha256:abc"}
        cases = {
            "missing required property": (missing_migrations, "<root>"),
            "non-sha256 image digest": (bad_digest, "images/auth"),
        }
        for name, (manifest, path) in cases.items():
            with self.subTest(name):
                code, output = self.run_validator(self.write(json.dumps(manifest)))
                self.assertEqual(code, 1, output)
                self.assertIn(path, output)
                self.assertIn("does not conform", output)

    def test_a_generated_at_that_is_not_rfc3339_exits_one(self) -> None:
        # Regression: the validator was built without a format checker, so the
        # schema's `format: date-time` was only an annotation and both of these
        # manifests validated and would have been published.
        cases = {
            "not a timestamp at all": "not-a-timestamp",
            "no RFC 3339 offset": "2026-11-01T00:00:00",
        }
        for name, generated_at in cases.items():
            with self.subTest(name):
                manifest = conforming_manifest()
                manifest["generated_at"] = generated_at
                code, output = self.run_validator(self.write(json.dumps(manifest)))
                self.assertEqual(code, 1, output)
                self.assertIn("generated_at", output)
                self.assertIn("date-time", output)

    def test_a_manifest_outside_the_checkout_exits_one(self) -> None:
        outside = self.root / "elsewhere.json"
        outside.write_text(json.dumps(conforming_manifest()), encoding="utf-8")
        code, output = self.run_validator(outside)
        self.assertEqual(code, 1, output)
        self.assertIn("must resolve inside", output)

    def test_a_schema_outside_the_checkout_exits_one(self) -> None:
        outside = self.root / "elsewhere-schema.json"
        outside.write_text(SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
        manifest = self.write(json.dumps(conforming_manifest()))
        code, output = self.run_validator(manifest, schema=outside)
        self.assertEqual(code, 1, output)
        self.assertIn("must resolve inside", output)


if __name__ == "__main__":
    unittest.main()
