"""Exercise the context stub artifact and the commands used by its CI gate."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from benchmark_test_support import ROOT, SCRIPTS, load_module

load = load_module("assemble_load", ROOT / "benchmarks/context/assemble_load.py")
VALIDATOR = load_module(
    "validate_published_context_assembly",
    SCRIPTS / "validate_published_context_assembly.py",
)
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


# Codacy excludes the repo's pytest-assert test trees (.codacy.yml), but
# benchmarks/scripts is outside them; the sibling gate tests there assert
# through unittest.TestCase methods. Assertion methods still raise plain
# AssertionError, so pytest keeps collecting these functions unchanged.
_CASES = unittest.TestCase()


def _run_harness(monkeypatch, stats, options) -> int:
    options = {"profile": "stub", "rps": "500", "max_error_rate": 0.0, **options}

    async def synthetic_run(*_args):
        return stats

    monkeypatch.setattr(load, "_run_stub", synthetic_run)
    monkeypatch.setattr(load, "_run_live", synthetic_run)
    monkeypatch.setattr(sys, "argv", [
        "assemble_load.py", "--profile", options["profile"], "--rps", str(options["rps"]),
        "--duration", "10",
        "--max-error-rate", str(options["max_error_rate"]), "--json", DATA_NAME,
    ])
    try:
        return load.main()
    except SystemExit as exc:
        return exc.code


def _run_validator(monkeypatch) -> tuple[int, str]:
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "argv", [
        "validate_published_context_assembly.py", "--strict", DATA_NAME,
    ])
    with contextlib.redirect_stderr(stderr):
        try:
            VALIDATOR.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
        except jsonschema.ValidationError as exc:
            # A CLI run would die on this traceback; mirror its final line.
            sys.stderr.write(f"{type(exc).__module__}.{type(exc).__name__}: {exc}\n")
            code = 1
    return code, stderr.getvalue()


def test_harness_serializes_and_validates_stub_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stats = load._DriveStats((1.0, 2.0, 3.0, 4.0), 5, 4, 1)
    _CASES.assertEqual(_run_harness(monkeypatch, stats, {"max_error_rate": 0.2}), 0)
    payload = json.loads(Path(DATA_NAME).read_text(encoding="utf-8"))
    _CASES.assertEqual(payload, EXPECTED)
    jsonschema.validate(payload, json.loads(SCHEMA.read_text(encoding="utf-8")))
    code, stderr = _run_validator(monkeypatch)
    _CASES.assertEqual(code, 0, stderr)


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
    _CASES.assertEqual(
        _run_harness(
            monkeypatch, stats,
            {"profile": profile, "max_error_rate": max_error_rate},
        ),
        expected,
    )


@pytest.mark.parametrize("rps", [-1, 0, 1, 2])
def test_harness_rps_artifact_schema_invariant(tmp_path, monkeypatch, rps):
    monkeypatch.chdir(tmp_path)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    minimum = schema["properties"]["rps"]["minimum"]
    stats = load._DriveStats((1.0,), 1, 1, 0)
    code = _run_harness(monkeypatch, stats, {"rps": str(rps)})
    if rps < minimum:
        _CASES.assertNotEqual(code, 0)
        _CASES.assertFalse(
            Path(DATA_NAME).exists(),
            f"rps={rps}: harness exited {code} but wrote {DATA_NAME}",
        )
    else:
        _CASES.assertEqual(code, 0)
        payload = json.loads(Path(DATA_NAME).read_text(encoding="utf-8"))
        _CASES.assertEqual(
            list(Draft202012Validator(schema).iter_errors(payload)),
            [],
            f"rps={rps}: harness wrote an artifact the schema rejects",
        )


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
    code, stderr = _run_validator(monkeypatch)
    _CASES.assertNotEqual(code, 0)
    _CASES.assertIn("ValidationError", stderr)


def test_validator_cli_rejects_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, stderr = _run_validator(monkeypatch)
    _CASES.assertNotEqual(code, 0)
    _CASES.assertIn("file not found", stderr)


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
    _CASES.assertNotEqual(exc.value.code, 0)
