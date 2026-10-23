"""Exercise the context stub artifact and the commands used by its CI gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from benchmark_test_support import ROOT, SCRIPTS, load_module

load = load_module("assemble_load", ROOT / "benchmarks/context/assemble_load.py")
SCHEMA = ROOT / "benchmarks/data-schema/context-assembly-benchmark-data.schema.json"
DATA_NAME = "context-assembly-benchmark-data.json"
EXPECTED = {
    "profile": "stub",
    "rps": 500,
    "duration_s": 10.0,
    "attempted": 5,
    "succeeded": 4,
    "failed": 1,
    "error_rate": 0.2,
    "mean_ms": 2.5,
    "p50_ms": 2.0,
    "p95_ms": 3.0,
    "p99_ms": 3.0,
}


def _run_harness(monkeypatch, stats, *, profile="stub", max_error_rate=0.0) -> int:
    async def synthetic_run(*_args):
        return stats

    monkeypatch.setattr(load, "_run_stub", synthetic_run)
    monkeypatch.setattr(load, "_run_live", synthetic_run)
    monkeypatch.setattr(sys, "argv", [
        "assemble_load.py", "--profile", profile, "--rps", "500", "--duration", "10",
        "--max-error-rate", str(max_error_rate), "--json", DATA_NAME,
    ])
    try:
        return load.main()
    except SystemExit as exc:
        return exc.code


def _validate_cli() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_published_context_assembly.py"),
         "--strict", DATA_NAME],
        capture_output=True,
        text=True,
        check=False,
    )


def test_harness_serializes_and_validates_stub_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stats = load._DriveStats((1.0, 2.0, 3.0, 4.0), 5, 4, 1)
    assert _run_harness(monkeypatch, stats, max_error_rate=0.2) == 0
    payload = json.loads(Path(DATA_NAME).read_text(encoding="utf-8"))
    assert payload == EXPECTED
    jsonschema.validate(payload, json.loads(SCHEMA.read_text(encoding="utf-8")))
    result = _validate_cli()
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("case", [
    ("stub", 49.99, 100, 0, 0.0, 0),
    ("stub", 50.0, 100, 0, 0.0, 1),
    ("stub", 50.01, 100, 0, 0.0, 1),
    ("stub", 1.0, 100, 1, 0.0, 1),
    ("stub", 1.0, 100, 1, 0.01, 0),
    ("stub", 1.0, 100, 1, 0.02, 0),
    ("live", 50.0, 100, 0, 0.0, 0),
    ("stub", 0.0, 100, 100, 0.0, 2),
])
def test_harness_gate_exit_codes(tmp_path, monkeypatch, case):
    profile, latency, attempted, failed, max_error_rate, expected = case
    monkeypatch.chdir(tmp_path)
    succeeded = attempted - failed
    stats = load._DriveStats((latency,) * succeeded, attempted, succeeded, failed)
    assert _run_harness(
        monkeypatch, stats, profile=profile, max_error_rate=max_error_rate,
    ) == expected


@pytest.mark.parametrize("field", EXPECTED)
def test_schema_requires_result_fields(field):
    payload = dict(EXPECTED)
    del payload[field]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


@pytest.mark.parametrize("field", EXPECTED)
def test_schema_rejects_wrong_field_types(field):
    payload = {**EXPECTED, field: []}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_schema_rejects_live_profile():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**EXPECTED, "profile": "live"}, schema)


@pytest.mark.parametrize("payload", [
    {key: value for key, value in EXPECTED.items() if key != "profile"},
    {**EXPECTED, "p99_ms": "invalid"},
])
def test_validator_cli_rejects_malformed_artifact(tmp_path, monkeypatch, payload):
    monkeypatch.chdir(tmp_path)
    Path(DATA_NAME).write_text(json.dumps(payload), encoding="utf-8")
    result = _validate_cli()
    assert result.returncode != 0
    assert "ValidationError" in result.stderr


def test_validator_cli_rejects_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _validate_cli()
    assert result.returncode != 0
    assert "file not found" in result.stderr


def test_strict_validator_requires_jsonschema(tmp_path, monkeypatch):
    validator = load_module(
        "validate_published_context_assembly",
        SCRIPTS / "validate_published_context_assembly.py",
    )
    monkeypatch.chdir(tmp_path)
    Path(DATA_NAME).write_text(json.dumps(EXPECTED), encoding="utf-8")
    monkeypatch.setattr(validator.published_suite_validate, "jsonschema", None)
    with pytest.raises(SystemExit) as exc:
        validator.main(["--strict", DATA_NAME])
    assert exc.value.code != 0
