#!/usr/bin/env python3
"""Tests for the release manifest generator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).with_name("release-manifest.py")
SPEC = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load release-manifest.py")
release_manifest = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_manifest
SPEC.loader.exec_module(release_manifest)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
COMMIT = "0123456789abcdef0123456789abcdef01234567"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "infra" / "release-manifest.schema.json"


@dataclass(frozen=True)
class CliCase:
    tag: str = "v1.2.3"
    services: str = "auth,proxy"
    digests: dict[str, str] | None = None
    map_path: Path | None = None
    output: Path | None = None


class ReleaseManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "services" / "auth").mkdir(parents=True)
        (self.root / "services" / "auth" / "Dockerfile").write_text("FROM scratch\n")
        (self.root / "services" / "proxy").mkdir(parents=True)
        (self.root / "services" / "proxy" / "Dockerfile").write_text("FROM scratch\n")
        (self.root / "services" / "api").mkdir(parents=True)
        self.openapi = self.root / "services" / "api" / "openapi.snapshot.json"
        self.openapi.write_text('{"openapi":"3.1.0"}\n')
        proto = self.root / "packages" / "proto" / "ibex" / "auth" / "v1"
        proto.mkdir(parents=True)
        (proto / "auth.proto").write_text('syntax = "proto3";\n')
        postgres = self.root / "infra" / "migrations" / "postgres"
        postgres.mkdir(parents=True)
        (postgres / "000001_init.up.sql").write_text("SELECT 1;\n")
        (postgres / "000002_next.up.sql").write_text("SELECT 2;\n")
        (postgres / "000002_next.down.sql").write_text("SELECT 0;\n")
        clickhouse = self.root / "infra" / "migrations" / "clickhouse"
        clickhouse.mkdir(parents=True)
        (clickhouse / "000001_usage.up.sql").write_text("SELECT 1;\n")
        self.digest_map = {"auth": DIGEST_A, "proxy": DIGEST_B}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self) -> dict[str, object]:
        return release_manifest.build_manifest(
            release_manifest.ManifestSpec(
                root=self.root,
                tag="v1.2.3",
                repository="Rick1330/ibex-harness",
                commit=COMMIT,
                generated_at="2026-11-01T00:00:00Z",
                digest_map=self.digest_map,
                services=["auth", "proxy"],
            )
        )

    def run_cli(self, case: CliCase | None = None) -> tuple[int, Path]:
        case = case or CliCase()
        map_path = case.map_path or self.root / "digests.json"
        map_path.write_text(
            json.dumps(self.digest_map if case.digests is None else case.digests)
        )
        output = case.output or self.root / "release-manifest.json"
        code = release_manifest.main(
            [
                "--root",
                str(self.root),
                "--tag",
                case.tag,
                "--commit",
                COMMIT,
                "--generated-at",
                "2026-11-01T00:00:00Z",
                "--digest-map",
                str(map_path),
                "--services",
                case.services,
                "--output",
                str(output),
            ]
        )
        return code, output

    def test_builds_the_expected_manifest(self) -> None:
        manifest = self.build()
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["tag"], "v1.2.3")
        self.assertEqual(manifest["platform_version"], "1.2.3")
        self.assertEqual(manifest["images"], {"auth": DIGEST_A, "proxy": DIGEST_B})
        self.assertEqual(manifest["migrations"], {"postgres": 2, "clickhouse": 1})
        self.assertEqual(manifest["bundles"], [])
        expected_openapi = hashlib.sha256(self.openapi.read_bytes()).hexdigest()
        contracts = manifest["contracts"]
        self.assertIsInstance(contracts, dict)
        self.assertEqual(contracts["openapi_sha256"], expected_openapi)
        self.assertRegex(contracts["proto_sha256"], r"^[0-9a-f]{64}$")

    def test_cli_writes_the_manifest(self) -> None:
        code, output = self.run_cli()
        self.assertEqual(code, 0)
        data = json.loads(output.read_text())
        self.assertEqual(data["platform_version"], "1.2.3")
        self.assertEqual(
            data["source"],
            {"repository": "Rick1330/ibex-harness", "commit": COMMIT},
        )

    def test_manifest_matches_the_published_schema(self) -> None:
        import jsonschema

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        manifests = [self.build(), json.loads(self.run_cli()[1].read_text())]
        for manifest in manifests:
            jsonschema.validate(manifest, schema)

    def test_rejects_an_invalid_tag(self) -> None:
        code, _ = self.run_cli(CliCase(tag="1.2.3"))
        self.assertEqual(code, 1)

    def test_rejects_a_missing_digest(self) -> None:
        code, _ = self.run_cli(CliCase(digests={"auth": DIGEST_A}))
        self.assertEqual(code, 1)

    def test_rejects_a_malformed_digest(self) -> None:
        code, _ = self.run_cli(
            CliCase(digests={"auth": "sha256:not-a-digest", "proxy": DIGEST_B})
        )
        self.assertEqual(code, 1)

    def test_rejects_a_missing_service_dockerfile(self) -> None:
        code, _ = self.run_cli(CliCase(services="auth,proxy,memory"))
        self.assertEqual(code, 1)

    def test_rejects_an_output_outside_the_root(self) -> None:
        code, _ = self.run_cli(
            CliCase(output=Path(tempfile.gettempdir()) / "escape.json")
        )
        self.assertEqual(code, 1)

    def test_rejects_a_digest_map_outside_the_root(self) -> None:
        outside = Path(tempfile.gettempdir()) / "digests-outside.json"
        code, _ = self.run_cli(CliCase(map_path=outside))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
