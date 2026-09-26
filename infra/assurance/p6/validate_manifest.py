#!/usr/bin/env python3
"""Validate an IBEX P6 bootstrap evidence manifest without external dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "infra/assurance/p6/manifest.schema.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ENVIRONMENTS = {"local", "preview", "staging", "production"}
APPLICABILITY = {"applicable", "inapplicable"}
RESULTS = {"passed", "failed", "skipped", "missing", "unknown", "cancelled"}


def fail(message: str) -> None:
    raise ValueError(message)


def require(mapping: dict[str, Any], *keys: str, where: str) -> None:
    for key in keys:
        if key not in mapping:
            fail(f"{where}: missing required field {key}")


def string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{where}: expected a non-empty string")
    return value


def validate(manifest: dict[str, Any]) -> None:
    require(
        manifest,
        "manifest_version",
        "run_id",
        "commit_sha",
        "environment",
        "topology",
        "artifacts",
        "versions",
        "checks",
        "rollback",
        "owner",
        where="manifest",
    )
    if manifest["manifest_version"] != "p6-bootstrap.v1":
        fail("manifest.manifest_version: unsupported version")
    if not COMMIT.fullmatch(string(manifest["commit_sha"], "manifest.commit_sha") ):
        fail("manifest.commit_sha: expected a 40-character lowercase SHA")
    if manifest["environment"] not in ENVIRONMENTS:
        fail("manifest.environment: unsupported environment")
    string(manifest["run_id"], "manifest.run_id")
    string(manifest["owner"], "manifest.owner")

    topology = manifest["topology"]
    if not isinstance(topology, dict):
        fail("manifest.topology: expected object")
    require(topology, "ui_origin", "api_origin", "sse_origin", where="manifest.topology")
    for key in ("ui_origin", "api_origin", "sse_origin"):
        string(topology[key], f"manifest.topology.{key}")

    versions = manifest["versions"]
    if not isinstance(versions, dict):
        fail("manifest.versions: expected object")
    require(versions, "fixture", "schema", "migration", where="manifest.versions")
    for key, value in versions.items():
        string(value, f"manifest.versions.{key}")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list):
        fail("manifest.artifacts: expected array")
    for index, artifact in enumerate(artifacts):
        where = f"manifest.artifacts[{index}]"
        if not isinstance(artifact, dict):
            fail(f"{where}: expected object")
        require(artifact, "name", "sha256", "uri", where=where)
        string(artifact["name"], f"{where}.name")
        digest = string(artifact["sha256"], f"{where}.sha256")
        if not SHA256.fullmatch(digest):
            fail(f"{where}.sha256: expected lowercase SHA-256")
        string(artifact["uri"], f"{where}.uri")

    checks = manifest["checks"]
    if not isinstance(checks, list) or not checks:
        fail("manifest.checks: expected a non-empty array")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        where = f"manifest.checks[{index}]"
        if not isinstance(check, dict):
            fail(f"{where}: expected object")
        require(check, "name", "expected", "applicability", "result", where=where)
        name = string(check["name"], f"{where}.name")
        if name in seen:
            fail(f"{where}.name: duplicate check name {name}")
        seen.add(name)
        if not isinstance(check["expected"], bool):
            fail(f"{where}.expected: expected boolean")
        applicability = check["applicability"]
        if applicability not in APPLICABILITY:
            fail(f"{where}.applicability: unsupported value")
        result = check["result"]
        if result not in RESULTS:
            fail(f"{where}.result: unsupported value")
        reason = check.get("reason")
        if applicability == "inapplicable":
            if not isinstance(reason, str) or not reason:
                fail(f"{where}: inapplicable checks require a reason")
            if result not in {"skipped", "missing"}:
                fail(f"{where}: inapplicable checks must be skipped or missing")
        elif check["expected"] and result in {"skipped", "missing"}:
            fail(f"{where}: expected applicable check cannot be {result}")

    rollback = manifest["rollback"]
    if not isinstance(rollback, dict):
        fail("manifest.rollback: expected object")
    require(
        rollback,
        "prior_digest",
        "current_digest",
        "schema_compatible",
        "command",
        "verified",
        where="manifest.rollback",
    )
    for key in ("prior_digest", "current_digest", "command"):
        string(rollback[key], f"manifest.rollback.{key}")
    for key in ("schema_compatible", "verified"):
        if not isinstance(rollback[key], bool):
            fail(f"manifest.rollback.{key}: expected boolean")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--sha256", action="store_true", help="also print the manifest digest")
    args = parser.parse_args()
    try:
        raw = args.manifest.read_bytes()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            fail("manifest: expected JSON object")
        validate(parsed)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"P6 manifest invalid: {exc}", file=sys.stderr)
        return 1
    print(f"P6 manifest valid: {args.manifest}")
    if args.sha256:
        print(hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
