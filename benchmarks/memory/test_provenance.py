"""Tests for the provenance contract: hashing, runner identity, and the schema widening."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_BENCH))

import provenance

_SCHEMA_DIR = _BENCH.parent / "data-schema"
_PUBLISHED_DIR = _BENCH.parents[1] / "site" / "public" / "benchmarks"
HNSW_SCHEMA_PATH = _SCHEMA_DIR / "hnsw-benchmark-data.schema.json"
RANKING_SCHEMA_PATH = _SCHEMA_DIR / "ranking-quality-benchmark-data.schema.json"
HNSW_PUBLISHED_PATH = _PUBLISHED_DIR / "hnsw-benchmark-data.json"
RANKING_PUBLISHED_PATH = _PUBLISHED_DIR / "ranking-quality-benchmark-data.json"

# sha256 of exact bytes, computed independently with sha256sum.
SIMPLE_DIGEST = "8c2ca5992e9dfd5334d4eb7eb32dcc3e61395ada9abc990f5992e639cdb76376"
CRLF_DIGEST = "4ad3ef64dfb83f7a8f789bce6f30cc1f8d18491b14db4c875309b150d2a7d213"
LF_DIGEST = "2751a3a2f303ad21752038085e2b8c5f98ecff61a2e4ebbd43506a941725be80"


def _jsonschema() -> Any:
    """Import jsonschema for the schema tests.

    CI installs it from ``.github/requirements/jsonschema.txt``. A venv without it skips these
    tests rather than failing the hashing ones, and the skip is reported, not silent.
    """
    return pytest.importorskip(
        "jsonschema", reason="schema contract tests need jsonschema"
    )


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _errors(schema: dict[str, Any], instance: Any) -> list[str]:
    validator = _jsonschema().Draft202012Validator(schema)
    return [error.message for error in validator.iter_errors(instance)]


def _hnsw_run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "sha": "0123456789abcdef0123456789abcdef01234567",
        "short_sha": "0123456",
        "timestamp": "2026-11-12T00:00:00Z",
        "branch": "main",
        "run_number": 1,
        "run_url": "https://example.invalid/actions/runs/1",
        "methodology": {"ef_search": 64},
        "mean_recall_at_10": 1.0,
        "results": [
            {
                "corpus_size": 10000,
                "query_count": 100,
                "recall_at_10": 1.0,
                "latency_ms_p50": 2.0,
                "latency_ms_p95": 3.0,
                "latency_ms_p99": 4.0,
                "ef_search": 64,
            }
        ],
    }
    run.update(overrides)
    return run


def _ranking_run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "sha": "0123456789abcdef0123456789abcdef01234567",
        "short_sha": "0123456",
        "timestamp": "2026-11-12T00:00:00Z",
        "branch": "main",
        "run_number": 1,
        "run_url": "https://example.invalid/actions/runs/1",
        "metrics": {"precision_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0},
        "status": "pass",
    }
    run.update(overrides)
    return run


def _hnsw_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "benchmark": "hnsw_recall_latency", "runs": [run]}


def _ranking_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "benchmark": "ranking_quality", "runs": [run]}


class TestFileSha256:
    def test_it_hashes_the_exact_bytes(self, tmp_path: Path) -> None:
        target = tmp_path / "payload.bin"
        target.write_bytes(b"ibex\n")

        assert provenance.file_sha256(target) == SIMPLE_DIGEST

    def test_it_does_not_normalise_line_endings(self, tmp_path: Path) -> None:
        # Text mode would turn the CRLF file into the LF one and hide a checkout difference.
        crlf = tmp_path / "crlf.txt"
        lf = tmp_path / "lf.txt"
        crlf.write_bytes(b"line1\r\nline2\r\n")
        lf.write_bytes(b"line1\nline2\n")

        assert provenance.file_sha256(crlf) == CRLF_DIGEST
        assert provenance.file_sha256(lf) == LF_DIGEST
        assert CRLF_DIGEST != LF_DIGEST

    def test_it_agrees_with_sha256sum(self) -> None:
        binary = shutil.which("sha256sum")
        if binary is None:
            pytest.skip("sha256sum is not installed")

        reported = subprocess.run(
            [binary, str(provenance.CORPUS_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        assert reported.stdout.split()[0] == provenance.file_sha256(
            provenance.CORPUS_PATH
        )

    def test_a_missing_file_raises_instead_of_hashing_nothing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(RuntimeError, match="missing input"):
            provenance.file_sha256(tmp_path / "absent.py")


class TestCorpusIdentity:
    def test_hnsw_manifest_names_both_source_hashes(self) -> None:
        _, manifest = provenance.corpus_identity("hnsw")
        synth_sha = hashlib.sha256(provenance.SYNTH_PATH.read_bytes()).hexdigest()
        corpus_sha = hashlib.sha256(provenance.CORPUS_PATH.read_bytes()).hexdigest()

        assert f"synth.py={synth_sha}" in manifest
        assert f"corpus.py={corpus_sha}" in manifest
        assert manifest.startswith("pgvector|")
        assert manifest.endswith("|dim=1024,active=64")

    def test_hnsw_hash_is_the_documented_concatenation(self) -> None:
        synth_sha = hashlib.sha256(provenance.SYNTH_PATH.read_bytes()).hexdigest()
        corpus_sha = hashlib.sha256(provenance.CORPUS_PATH.read_bytes()).hexdigest()
        expected = hashlib.sha256(
            f"pgvector|{synth_sha}|{corpus_sha}|dim=1024,active=64".encode()
        ).hexdigest()

        corpus_hash = provenance.corpus_identity("hnsw")[0]

        assert corpus_hash == expected
        assert len(corpus_hash) == 64
        assert corpus_hash == corpus_hash.lower()

    def test_hnsw_hash_covers_the_bytes_of_each_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline, _ = provenance.corpus_identity("hnsw")
        synth_copy = tmp_path / "synth.py"
        synth_copy.write_bytes(provenance.SYNTH_PATH.read_bytes() + b"\n# drift\n")
        monkeypatch.setattr(provenance, "SYNTH_PATH", synth_copy)

        drifted, manifest = provenance.corpus_identity("hnsw")

        assert drifted != baseline
        assert (
            f"synth.py={hashlib.sha256(synth_copy.read_bytes()).hexdigest()}"
            in manifest
        )

    def test_gold_hash_is_the_gold_set_file_digest(self) -> None:
        corpus_hash, manifest = provenance.corpus_identity("gold")

        assert corpus_hash == provenance.file_sha256(provenance.GOLD_SET_PATH)
        assert manifest == f"gold_set_v2.json={corpus_hash}"

    def test_the_v1_gold_hash_is_the_v1_file_digest(self) -> None:
        corpus_hash, manifest = provenance.corpus_identity("gold_v1")

        assert corpus_hash == provenance.file_sha256(provenance.GOLD_V1_SET_PATH)
        assert manifest == f"gold_set_v1.json={corpus_hash}"

    def test_the_v1_gold_hash_agrees_with_sha256sum(self) -> None:
        binary = shutil.which("sha256sum")
        if binary is None:
            pytest.skip("sha256sum is not installed")

        reported = subprocess.run(
            [binary, str(provenance.GOLD_V1_SET_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        v1_hash = provenance.corpus_identity("gold_v1")[0]

        assert reported.stdout.split()[0] == v1_hash

    def test_the_two_gold_sets_are_different_corpora(self) -> None:
        # The reason the kind exists: a v1 run must not publish the v2 identity, and adding it
        # must not move what "gold" already means.
        v2_hash, v2_manifest = provenance.corpus_identity("gold")
        v1_hash, v1_manifest = provenance.corpus_identity("gold_v1")

        assert v1_hash != v2_hash
        assert v2_manifest.startswith("gold_set_v2.json=")
        assert v1_manifest.startswith("gold_set_v1.json=")

    def test_gold_v1_hashes_the_bytes_of_the_v1_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline, _ = provenance.corpus_identity("gold_v1")
        copy = tmp_path / "gold_set_v1.json"
        copy.write_bytes(provenance.GOLD_V1_SET_PATH.read_bytes() + b"\n")
        monkeypatch.setattr(provenance, "GOLD_V1_SET_PATH", copy)

        drifted, manifest = provenance.corpus_identity("gold_v1")

        assert drifted != baseline
        assert manifest == f"gold_set_v1.json={drifted}"

    def test_an_unknown_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown corpus kind"):
            provenance.corpus_identity("goldset")


class TestRunnerIdentity:
    def test_it_reports_usable_hardware(self) -> None:
        identity = provenance.runner_identity()

        assert isinstance(identity["runner_cpu_model"], str)
        assert identity["runner_cpu_model"].strip()
        assert isinstance(identity["runner_cpu_count"], int)
        assert identity["runner_cpu_count"] >= 1
        assert isinstance(identity["runner_ram_mib"], int)
        assert identity["runner_ram_mib"] >= 1

    def test_environment_overrides_win(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(provenance.ENV_RUNNER_CPU, "Test CPU 9000")
        monkeypatch.setenv(provenance.ENV_RUNNER_RAM_MIB, "4096")

        identity = provenance.runner_identity()

        assert identity["runner_cpu_model"] == "Test CPU 9000"
        assert identity["runner_ram_mib"] == 4096

    def test_a_malformed_override_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(provenance.ENV_RUNNER_RAM_MIB, "16GiB")

        with pytest.raises(RuntimeError, match="positive integer"):
            provenance.runner_identity()

    def test_an_empty_cpu_override_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(provenance.ENV_RUNNER_CPU, "   ")

        with pytest.raises(RuntimeError, match="is empty"):
            provenance.runner_identity()


class TestWorkingTreeState:
    def test_is_dirty_returns_a_bool(self) -> None:
        assert isinstance(provenance.is_dirty(), bool)

    def test_it_fails_closed_outside_a_repository(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(provenance, "_REPO_ROOT", tmp_path)

        assert provenance.is_dirty() is True
        assert provenance.corpus_status("hnsw") == "stale"

    def test_corpus_status_is_one_of_the_schema_values(self) -> None:
        assert provenance.corpus_status("hnsw") in {"current", "stale"}
        assert provenance.corpus_status("gold") in {"current", "stale"}


class TestProvenanceRecord:
    def test_the_hnsw_record_is_complete_and_consistent(self) -> None:
        record = provenance.provenance_record("hnsw")
        corpus_hash, manifest = provenance.corpus_identity("hnsw")

        assert record["status"] == "recorded"
        assert record["producer"] == provenance.PRODUCER
        assert record["corpus_hash"] == corpus_hash
        assert record["corpus_hash_algo"] == "sha256"
        assert record["corpus_manifest"] == manifest
        assert record["dirty"] in {True, False}
        assert record["runner_cpu_count"] >= 1
        assert record["runner_ram_mib"] >= 1
        assert record["runner_cpu_model"]
        assert "gold_set_hash" not in record

    def test_the_gold_record_names_the_gold_set(self) -> None:
        record = provenance.provenance_record("gold")

        assert record["gold_set_name"] == "gold_set_v2.json"
        assert record["gold_set_hash"] == record["corpus_hash"]
        assert record["gold_set_hash"] == provenance.file_sha256(
            provenance.GOLD_SET_PATH
        )

    def test_the_v1_gold_record_names_the_v1_gold_set(self) -> None:
        record = provenance.provenance_record("gold_v1")

        assert record["gold_set_name"] == "gold_set_v1.json"
        assert record["gold_set_hash"] == record["corpus_hash"]
        assert record["gold_set_hash"] == provenance.file_sha256(
            provenance.GOLD_V1_SET_PATH
        )
        assert record["corpus_manifest"] == f"gold_set_v1.json={record['corpus_hash']}"
        assert record["corpus_status"] in {"current", "stale"}

    def test_an_unknown_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown corpus kind"):
            provenance.provenance_record("HNSW")

    def test_only_the_three_recorded_kinds_are_accepted(self) -> None:
        # A near miss ("gold-v1", "gold_v1 ") must not hash something plausible instead.
        assert provenance.KINDS == ("hnsw", "gold", "gold_v1")

        for kind in ("gold-v1", "goldV1", "gold_v2", "gold_v1 "):
            with pytest.raises(ValueError, match="unknown corpus kind"):
                provenance.corpus_identity(kind)
            with pytest.raises(ValueError, match="unknown corpus kind"):
                provenance.provenance_record(kind)


class TestSchemaWidening:
    def test_both_schemas_stay_at_version_one(self) -> None:
        for path in (HNSW_SCHEMA_PATH, RANKING_SCHEMA_PATH):
            schema = _schema(path)

            assert schema["properties"]["schema_version"] == {"const": 1}
            assert schema["description"], f"{path.name} must say why it did not bump"

    def test_provenance_stays_optional_so_old_runs_validate(self) -> None:
        hnsw = _schema(HNSW_SCHEMA_PATH)["properties"]["runs"]["items"]
        ranking = _schema(RANKING_SCHEMA_PATH)["properties"]["runs"]["items"]

        assert "provenance" in hnsw["properties"]
        assert "provenance" in ranking["properties"]
        assert "provenance" not in hnsw["required"]
        assert "provenance" not in ranking["required"]
        assert _errors(_schema(HNSW_SCHEMA_PATH), _hnsw_payload(_hnsw_run())) == []
        assert (
            _errors(_schema(RANKING_SCHEMA_PATH), _ranking_payload(_ranking_run()))
            == []
        )

    def test_the_committed_hnsw_history_still_validates(self) -> None:
        payload = json.loads(HNSW_PUBLISHED_PATH.read_text(encoding="utf-8"))

        assert _errors(_schema(HNSW_SCHEMA_PATH), payload) == []
        assert payload["runs"], "published history should not be empty"

    def test_the_committed_ranking_history_still_validates(self) -> None:
        payload = json.loads(RANKING_PUBLISHED_PATH.read_text(encoding="utf-8"))

        assert _errors(_schema(RANKING_SCHEMA_PATH), payload) == []
        assert payload["runs"], "published history should not be empty"

    def test_a_recorded_hnsw_block_is_accepted(self) -> None:
        record = provenance.provenance_record("hnsw")
        payload = _hnsw_payload(_hnsw_run(provenance=record))

        assert _errors(_schema(HNSW_SCHEMA_PATH), payload) == []

    def test_a_recorded_ranking_block_is_accepted(self) -> None:
        record = provenance.provenance_record("gold")
        payload = _ranking_payload(_ranking_run(provenance=record))

        assert _errors(_schema(RANKING_SCHEMA_PATH), payload) == []

    def test_a_recorded_v1_gold_block_is_accepted(self) -> None:
        # The block the legacy v1 producer now publishes has to pass the same schema.
        record = provenance.provenance_record("gold_v1")
        payload = _ranking_payload(_ranking_run(gold_set="v1", provenance=record))

        assert _errors(_schema(RANKING_SCHEMA_PATH), payload) == []
        assert record["gold_set_name"] == "gold_set_v1.json"

    def test_an_unrecorded_block_needs_only_its_status(self) -> None:
        run = _hnsw_run(provenance={"status": "unrecorded"})

        assert _errors(_schema(HNSW_SCHEMA_PATH), _hnsw_payload(run)) == []

    def test_a_recorded_block_without_corpus_hash_is_rejected(self) -> None:
        record = provenance.provenance_record("hnsw")
        del record["corpus_hash"]

        errors = _errors(
            _schema(HNSW_SCHEMA_PATH), _hnsw_payload(_hnsw_run(provenance=record))
        )

        assert any("corpus_hash" in message for message in errors)

    def test_a_recorded_block_with_a_malformed_corpus_hash_is_rejected(self) -> None:
        record = provenance.provenance_record("hnsw")
        schema = _schema(HNSW_SCHEMA_PATH)

        for bad in ("0" * 63, "A" * 64, "sha256:" + "0" * 64):
            payload = _hnsw_payload(
                _hnsw_run(provenance={**record, "corpus_hash": bad})
            )
            errors = _errors(schema, payload)
            assert errors, f"corpus_hash {bad!r} should be rejected"

    def test_a_recorded_block_with_an_unknown_field_is_rejected(self) -> None:
        record = provenance.provenance_record("hnsw")
        record["note"] = "hand written"

        errors = _errors(
            _schema(HNSW_SCHEMA_PATH), _hnsw_payload(_hnsw_run(provenance=record))
        )

        assert any("note" in message for message in errors)

    def test_a_recorded_block_missing_runner_ram_is_rejected(self) -> None:
        record = provenance.provenance_record("hnsw")
        del record["runner_ram_mib"]

        errors = _errors(
            _schema(HNSW_SCHEMA_PATH), _hnsw_payload(_hnsw_run(provenance=record))
        )

        assert any("runner_ram_mib" in message for message in errors)

    def test_the_ranking_schema_checks_the_gold_set_hash(self) -> None:
        schema = _schema(RANKING_SCHEMA_PATH)
        record = provenance.provenance_record("gold")
        assert record["gold_set_hash"]

        assert _errors(schema, _ranking_payload(_ranking_run(provenance=record))) == []
        bad = {**record, "gold_set_hash": "not-a-hash"}
        assert _errors(schema, _ranking_payload(_ranking_run(provenance=bad)))

    def test_a_recorded_block_without_the_gold_fields_passes_the_ranking_schema(
        self,
    ) -> None:
        # gold_set_hash/gold_set_name are optional: only this corpus kind knows the filename.
        record = provenance.provenance_record("hnsw") | {"seed": 7}
        payload = _ranking_payload(_ranking_run(provenance=record))

        assert _errors(_schema(RANKING_SCHEMA_PATH), payload) == []
