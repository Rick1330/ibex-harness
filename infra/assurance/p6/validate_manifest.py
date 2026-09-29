#!/usr/bin/env python3
"""Validate an IBEX P6 bootstrap evidence manifest without external dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "infra/assurance/p6/manifest.schema.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_URI = re.compile(r"^(https://|s3://|gs://|file://).+")
ENVIRONMENTS = {"local", "preview", "staging", "production"}
APPLICABILITY = {"applicable", "inapplicable"}
RESULTS = {"passed", "failed", "skipped", "missing", "unknown", "cancelled"}
EVIDENCE_STATES = {
    "declared",
    "mounted",
    "contract-tested",
    "runtime-tested",
    "staging-verified",
    "blocked",
}


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


def enum(value: Any, allowed: set[str], where: str, label: str) -> str:
    value = string(value, where)
    if value not in allowed:
        fail(f"{where}: unsupported {label} value")
    return value


def _validate_top_level(manifest: dict[str, Any]) -> None:
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
    commit_sha = string(manifest["commit_sha"], "manifest.commit_sha")
    if not COMMIT.fullmatch(commit_sha):
        fail("manifest.commit_sha: expected a 40-character lowercase SHA")
    enum(manifest["environment"], ENVIRONMENTS, "manifest.environment", "environment")
    string(manifest["run_id"], "manifest.run_id")
    string(manifest["owner"], "manifest.owner")


def _validate_topology(topology: Any) -> None:
    if not isinstance(topology, dict):
        fail("manifest.topology: expected object")
    require(topology, "ui_origin", "api_origin", "sse_origin", where="manifest.topology")
    for key in ("ui_origin", "api_origin", "sse_origin"):
        string(topology[key], f"manifest.topology.{key}")


def _validate_versions(versions: Any) -> None:
    if not isinstance(versions, dict):
        fail("manifest.versions: expected object")
    require(versions, "fixture", "schema", "migration", where="manifest.versions")
    for key, value in versions.items():
        string(value, f"manifest.versions.{key}")


def _validate_artifacts(artifacts: Any) -> dict[str, str]:
    if not isinstance(artifacts, list):
        fail("manifest.artifacts: expected array")
    declared: dict[str, str] = {}
    for index, artifact in enumerate(artifacts):
        where = f"manifest.artifacts[{index}]"
        if not isinstance(artifact, dict):
            fail(f"{where}: expected object")
        require(artifact, "name", "sha256", "uri", "evidence_state", where=where)
        string(artifact["name"], f"{where}.name")
        digest = string(artifact["sha256"], f"{where}.sha256")
        if not SHA256.fullmatch(digest):
            fail(f"{where}.sha256: expected lowercase SHA-256")
        uri = string(artifact["uri"], f"{where}.uri")
        if not ARTIFACT_URI.fullmatch(uri):
            fail(f"{where}.uri: unsupported immutable artifact URI")
        state = enum(
            artifact["evidence_state"], EVIDENCE_STATES, f"{where}.evidence_state", "evidence_state"
        )
        declared[uri] = state
    return declared


def _validate_check_artifacts(
    check: dict[str, Any], where: str, declared: dict[str, str]
) -> None:
    raw_uris = check.get("artifact_uris", [])
    if not isinstance(raw_uris, list):
        fail(f"{where}.artifact_uris: expected array")
    uris = [string(uri, f"{where}.artifact_uris[{i}]") for i, uri in enumerate(raw_uris)]
    for uri in uris:
        _validate_artifact_reference(uri, where, declared)
    _reject_blocked_only_contract_evidence(check, where, uris, declared)
    if check["applicability"] != "applicable":
        return
    if not check["expected"]:
        return
    if uris:
        return
    fail(f"{where}: applicable expected checks require artifact_uris")


def _validate_artifact_reference(uri: str, where: str, declared: dict[str, str]) -> None:
    if not ARTIFACT_URI.fullmatch(uri):
        fail(f"{where}.artifact_uris: unsupported artifact URI")
    if uri not in declared:
        fail(f"{where}.artifact_uris: URI is not declared in manifest.artifacts")


def _reject_blocked_only_contract_evidence(
    check: dict[str, Any], where: str, uris: list[str], declared: dict[str, str]
) -> None:
    if check.get("result") != "passed":
        return
    if check.get("evidence_state") != "contract-tested":
        return
    if not uris:
        return
    if all(declared[uri] == "blocked" for uri in uris):
        fail(f"{where}: contract-tested evidence cannot rely only on blocked artifacts")


@dataclass(frozen=True, slots=True)
class _CheckCore:
    name: str
    expected: bool
    applicability: str
    result: str


def _read_check(check: dict[str, Any], where: str) -> _CheckCore:
    require(
        check,
        "name",
        "expected",
        "applicability",
        "result",
        "evidence_state",
        where=where,
    )
    name = string(check["name"], f"{where}.name")
    if not isinstance(check["expected"], bool):
        fail(f"{where}.expected: expected boolean")
    applicability = enum(
        check["applicability"], APPLICABILITY, f"{where}.applicability", "applicability"
    )
    result = enum(check["result"], RESULTS, f"{where}.result", "result")
    enum(check["evidence_state"], EVIDENCE_STATES, f"{where}.evidence_state", "evidence_state")
    return _CheckCore(name, check["expected"], applicability, result)


def _validate_check_outcome(check: dict[str, Any], where: str, core: _CheckCore) -> None:
    if core.applicability == "inapplicable":
        _validate_inapplicable_check(check, where, core)
        return
    if core.result != "passed":
        fail(f"{where}: applicable checks must pass; got {core.result}")


def _validate_inapplicable_check(
    check: dict[str, Any], where: str, core: _CheckCore
) -> None:
    if core.expected:
        fail(f"{where}: inapplicable checks cannot be expected")
    reason = check.get("reason")
    if not isinstance(reason, str) or not reason:
        fail(f"{where}: inapplicable checks require a reason")
    if core.result not in {"skipped", "missing"}:
        fail(f"{where}: inapplicable checks must be skipped or missing")


def _validate_expected_evidence(check: dict[str, Any], where: str, core: _CheckCore) -> None:
    if not core.expected:
        return
    if check["evidence_state"] in {"blocked", "declared"}:
        fail(f"{where}: expected check is not executable evidence")


def _validate_one_check(
    check: dict[str, Any], where: str, declared: dict[str, str], seen: set[str]
) -> None:
    core = _read_check(check, where)
    if core.name in seen:
        fail(f"{where}.name: duplicate check name {core.name}")
    seen.add(core.name)
    _validate_check_artifacts(check, where, declared)
    _validate_check_outcome(check, where, core)
    _validate_expected_evidence(check, where, core)


def _validate_checks(checks: Any, declared: dict[str, str]) -> None:
    if not isinstance(checks, list) or not checks:
        fail("manifest.checks: expected a non-empty array")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        where = f"manifest.checks[{index}]"
        if not isinstance(check, dict):
            fail(f"{where}: expected object")
        _validate_one_check(check, where, declared, seen)


def _validate_rollback(rollback: Any) -> None:
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


def validate(manifest: dict[str, Any]) -> None:
    _validate_top_level(manifest)
    _validate_topology(manifest["topology"])
    _validate_versions(manifest["versions"])
    declared_uris = _validate_artifacts(manifest["artifacts"])
    _validate_checks(manifest["checks"], declared_uris)
    _validate_rollback(manifest["rollback"])


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
    except (OSError, TypeError, ValueError) as exc:
        print(f"P6 manifest invalid: {exc}", file=sys.stderr)
        return 1
    print(f"P6 manifest valid: {args.manifest}")
    if args.sha256:
        print(hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
