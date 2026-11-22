#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from benchmark_test_support import ROOT, SCRIPTS, TESTDATA, load_module

build_benchmark_data = load_module("build_benchmark_data", SCRIPTS / "build_benchmark_data.py")
validate_published_data = load_module(
    "validate_published_data",
    SCRIPTS / "validate_published_data.py",
)
validate_published_hnsw = load_module(
    "validate_published_hnsw",
    SCRIPTS / "validate_published_hnsw.py",
)
benchmark_constants = load_module("benchmark_constants", SCRIPTS / "benchmark_constants.py")


def _minimal_benchmark_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "sha": "a" * 40,
        "short_sha": "aaaaaaa",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "branch": "main",
        "status": "pass",
        "k6": {"p99_ms": 4.0, "error_rate": 0.0},
    }
    run.update(overrides)
    return run


def _assert_validate_rejects(payload: dict[str, object]) -> None:
    try:
        validate_published_data.validate_payload(payload)
    except SystemExit:
        return
    raise AssertionError("expected validate_payload to raise SystemExit")


def _invalid_payload_cases() -> list[tuple[str, dict[str, object]]]:
    proxy_bench = benchmark_constants.PROXY_OVERHEAD_BENCHMARK
    return [
        (
            "empty baseline_sha",
            {
                "schema_version": 1,
                "baseline_sha": "",
                "runs": [_minimal_benchmark_run()],
            },
        ),
        (
            "run_id as run_number",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        pr_number=None,
                        run_number=28594093144,
                        run_url="https://github.com/Rick1330/ibex-harness/actions/runs/28594093144",
                    ),
                ],
            },
        ),
        (
            f"missing {proxy_bench}",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        go_benchmarks={"BenchmarkOther": {"ns_per_op": 100.0}},
                    ),
                ],
            },
        ),
        (
            "non-positive ns_per_op",
            {
                "schema_version": 1,
                "baseline_sha": "bfc0a75",
                "runs": [
                    _minimal_benchmark_run(
                        go_benchmarks={proxy_bench: {"ns_per_op": 0}},
                    ),
                ],
            },
        ),
    ]


class ValidatePublishedDataTests(unittest.TestCase):
    def test_validate_published_data_accepts_seed_file(self) -> None:
        seed = ROOT / "site/public/benchmarks/benchmark-data.json"
        if not seed.exists():
            self.skipTest("published benchmark seed not available")
        validate_published_data.validate_payload(
            json.loads(seed.read_text(encoding="utf-8"))
        )

    def test_validate_published_data_rejects_path_traversal(self) -> None:
        with self.assertRaises(SystemExit):
            validate_published_data.resolve_benchmark_data_path("../../etc/passwd")

    def test_compare_pr_benchmark_json_accepts_matching_payloads(self) -> None:
        compare = load_module("compare_pr_benchmark_json", SCRIPTS / "compare_pr_benchmark_json.py")
        seed = ROOT / "site/public/benchmarks/benchmark-data.json"
        if not seed.exists():
            self.skipTest("published benchmark seed not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            committed = root / "site/public/benchmarks"
            artifact = root / "benchmarks/output"
            committed.mkdir(parents=True)
            artifact.mkdir(parents=True)
            shutil.copy(seed, committed / "benchmark-data.json")
            shutil.copy(seed, artifact / "benchmark-data.json")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(compare.main(), 0)
            finally:
                os.chdir(cwd)

    def test_resolve_output_baseline_sha_inherits_from_prev_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "benchmarks" / "output"
            data_schema = Path(tmp) / "benchmarks" / "data-schema"
            out.mkdir(parents=True)
            data_schema.mkdir(parents=True)
            shutil.copy(TESTDATA / "latest-pass.json", out / "latest.json")
            (data_schema / "baseline.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "baseline": {
                            "target_commit": "unset",
                            "baseline_sha": "unset",
                            "proxy_overhead_p99_ms": 20.0,
                            "throughput_rps": 0.0,
                            "allocs_per_op": 0.0,
                            "bytes_per_op": 0.0,
                        },
                        "policy": {
                            "max_regression_pct": 20.0,
                            "max_proxy_overhead_p99_ms": 20.0,
                            "max_error_rate": 0.001,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (out / "prev-benchmark-data.json").write_text(
                '{"schema_version":1,"baseline_sha":"bfc0a75","runs":[]}',
                encoding="utf-8",
            )
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                build_benchmark_data.OUT_DIR = out
                build_benchmark_data.BASELINE_PATH = data_schema / "baseline.json"
                latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
                resolved = build_benchmark_data.resolve_output_baseline_sha(latest, [])
                self.assertEqual(resolved, "bfc0a75")
            finally:
                os.chdir(cwd)

    def test_validate_published_data_rejects_invalid_payloads(self) -> None:
        for name, payload in _invalid_payload_cases():
            with self.subTest(name=name):
                _assert_validate_rejects(payload)

    def test_validate_published_data_rejects_duplicate_pr_number(self) -> None:
        payload = {
            "schema_version": 1,
            "baseline_sha": "bfc0a75",
            "runs": [
                {
                    "sha": "a" * 40,
                    "short_sha": "aaaaaaa",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "branch": "main",
                    "pr_number": 1,
                    "status": "pass",
                    "k6": {"p99_ms": 4.0, "error_rate": 0.0},
                },
                {
                    "sha": "b" * 40,
                    "short_sha": "bbbbbbb",
                    "timestamp": "2026-01-02T00:00:00+00:00",
                    "branch": "main",
                    "pr_number": 1,
                    "status": "pass",
                    "k6": {"p99_ms": 4.0, "error_rate": 0.0},
                },
            ],
        }
        _assert_validate_rejects(payload)

    def test_validate_published_hnsw_parse_args_strict_flag(self) -> None:
        path, strict = validate_published_hnsw.parse_args(
            ["--strict", "site/public/benchmarks/hnsw-benchmark-data.json"]
        )
        if path != "site/public/benchmarks/hnsw-benchmark-data.json" or strict is not True:
            raise AssertionError("expected --strict path parse")
        path, strict = validate_published_hnsw.parse_args(
            ["site/public/benchmarks/hnsw-benchmark-data.json"]
        )
        if strict is not False:
            raise AssertionError("expected non-strict default")

    def test_validate_published_hnsw_strict_fails_without_jsonschema(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _blocked(name: str, *args: object, **kwargs: object):
            if name == "jsonschema":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = _blocked  # type: ignore[method-assign]
        try:
            try:
                validate_published_hnsw.validate_against_json_schema({}, strict=True)
            except SystemExit:
                return
            raise AssertionError("strict mode should fail without jsonschema")
        finally:
            builtins.__import__ = real_import  # type: ignore[method-assign]


try:
    import jsonschema
except ImportError:  # pragma: no cover - CI installs it from .github/requirements/jsonschema.txt
    jsonschema = None


SCHEMA_DIR = ROOT / "benchmarks" / "data-schema"
PUBLISHED_DIR = ROOT / "site" / "public" / "benchmarks"

_SCHEMA_CASES = (
    ("hnsw-benchmark-data.schema.json", "hnsw-benchmark-data.json"),
    ("ranking-quality-benchmark-data.schema.json", "ranking-quality-benchmark-data.json"),
)


@unittest.skipIf(jsonschema is None, "jsonschema is required for schema contract tests")
class ProvenanceSchemaWideningTests(unittest.TestCase):
    """The published runs carry a ``provenance`` block; the schemas must declare it precisely.

    Regression guard for the CI failure where the memory workflow validated the full published
    files against ``additionalProperties: false`` run schemas that predated the widening: the
    field is declared at ``runs.items`` and stays strictly typed, rather than loosening the
    schema to accept anything.
    """

    def _schema(self, name: str) -> dict[str, Any]:
        return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))

    def _published(self, name: str) -> dict[str, Any]:
        return json.loads((PUBLISHED_DIR / name).read_text(encoding="utf-8"))

    def test_provenance_is_declared_at_run_level_without_loosening_the_schema(self) -> None:
        for schema_name, _ in _SCHEMA_CASES:
            with self.subTest(schema=schema_name):
                runs_items = self._schema(schema_name)["properties"]["runs"]["items"]
                self.assertIs(runs_items["additionalProperties"], False)
                self.assertIn("provenance", runs_items["properties"])
                provenance = runs_items["properties"]["provenance"]
                self.assertIs(provenance["additionalProperties"], False)

    def test_published_files_validate(self) -> None:
        for schema_name, data_name in _SCHEMA_CASES:
            with self.subTest(data=data_name):
                jsonschema.validate(
                    instance=self._published(data_name),
                    schema=self._schema(schema_name),
                )

    def test_a_malformed_provenance_block_is_rejected(self) -> None:
        schema = self._schema("hnsw-benchmark-data.schema.json")
        payload = self._published("hnsw-benchmark-data.json")
        run = next(run for run in payload["runs"] if "provenance" in run)
        run["provenance"]["corpus_hash"] = "not-a-sha256"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=payload, schema=schema)

    def test_a_recorded_block_missing_required_identity_is_rejected(self) -> None:
        schema = self._schema("ranking-quality-benchmark-data.schema.json")
        payload = self._published("ranking-quality-benchmark-data.json")
        run = next(run for run in payload["runs"] if "provenance" in run)
        del run["provenance"]["gold_set_hash"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=payload, schema=schema)


if __name__ == "__main__":
    unittest.main()
