"""Tests for publishing a run's provenance: required on the way in, restated on the way out.

Two publishers consume the raw artifacts: ``build_published_data`` for HNSW recall/latency and
``publish_quality_common.merge_ranking_quality_entry`` for ranking quality. Both must refuse a raw
artifact that cannot say what produced it, and the HNSW one must not claim an older corpus is the
current one. Neither schema makes the block required -- that is what keeps historical files
valid -- so the rule lives in the publishers and is tested here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_BENCH = Path(__file__).resolve().parent
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

import provenance
from build_published_data import RunMeta, _merge_entry
from publish_quality_common import (
    REQUIRED_PROVENANCE_FIELDS,
    merge_ranking_quality_entry,
)
from publish_quality_common import (
    RunMeta as QualityRunMeta,
)

_SCHEMA_DIR = _BENCH.parent / "data-schema"

_RECORDED: dict[str, Any] = {
    "status": "recorded",
    "producer": "benchmarks/memory/provenance.py",
    "runner_cpu_model": "test-cpu",
    "runner_cpu_count": 4,
    "runner_ram_mib": 8192,
    "corpus_hash_algo": "sha256",
    "corpus_manifest": "pgvector|synth.py=0|corpus.py=0|dim=1024,active=64",
    "corpus_status": "current",
    "dirty": False,
}


def _provenance(**overrides: Any) -> dict[str, Any]:
    """A complete recorded block; ``corpus_hash`` defaults to the corpus in this checkout."""
    record = dict(_RECORDED)
    record["corpus_hash"] = provenance.corpus_identity("hnsw")[0]
    record.update(overrides)
    return record


def _raw(provenance_record: Any = None, *, include: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": "2026-11-12T00:00:00+00:00",
        "methodology": {"ef_search": 64},
        "results": [
            {
                "corpus_size": 10_000,
                "query_count": 100,
                "recall_at_10": 1.0,
                "latency_ms_p50": 2.0,
                "latency_ms_p95": 3.0,
                "latency_ms_p99": 4.0,
                "ef_search": 64,
                "min_similarity": 0.70,
                "iterative_scan": "off",
                "index_build_mode": "bulk",
            }
        ],
    }
    if include:
        payload["provenance"] = _provenance() if provenance_record is None else provenance_record
    return payload


def _meta() -> RunMeta:
    return RunMeta(
        sha="0123456789abcdef0123456789abcdef01234567",
        branch="main",
        run_number=7,
        run_url="https://example.invalid/actions/runs/7",
    )


class TestHnswPublisher:
    def test_the_raw_provenance_is_published(self) -> None:
        record = _provenance(dirty=True)

        entry = _merge_entry(_raw(record), _meta())

        assert entry["provenance"] == record

    def test_a_raw_artifact_without_provenance_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match="raw artifact has no provenance; re-run the bench"):
            _merge_entry(_raw(include=False), _meta())

    def test_an_empty_provenance_block_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match="has no provenance"):
            _merge_entry(_raw({}), _meta())

    def test_an_incomplete_provenance_block_is_refused(self) -> None:
        # A half-written block would publish a corpus hash next to no runner identity, which
        # reads as a reproducible measurement when it is not one.
        record = _provenance()
        del record["runner_ram_mib"]

        with pytest.raises(RuntimeError, match="incomplete \\(missing runner_ram_mib\\)"):
            _merge_entry(_raw(record), _meta())

    def test_a_run_on_the_current_corpus_is_published_as_current(self) -> None:
        entry = _merge_entry(_raw(_provenance()), _meta())

        assert entry["provenance"]["corpus_status"] == "current"

    def test_a_run_on_an_older_corpus_is_published_as_stale(self) -> None:
        # Publishing an older measurement is legitimate; claiming it measured today's corpus is
        # not, so the run is published and the claim is corrected.
        entry = _merge_entry(_raw(_provenance(corpus_hash="0" * 64)), _meta())

        assert entry["provenance"]["corpus_status"] == "stale"
        assert entry["provenance"]["corpus_hash"] == "0" * 64

    def test_the_status_follows_the_hash_both_ways(self) -> None:
        # The one rule a reader can re-derive: current exactly when the hash is the corpus here.
        # A run that recorded "stale" before its corpus was committed is published as current,
        # because the bytes it hashed are the bytes in this checkout; the run's own `dirty` flag
        # still records the state of the tree it was measured on.
        entry = _merge_entry(_raw(_provenance(corpus_status="stale")), _meta())

        assert entry["provenance"]["corpus_status"] == "current"
        assert entry["provenance"]["dirty"] is False

    def test_the_published_entry_still_carries_the_gate_result(self) -> None:
        entry = _merge_entry(_raw(), _meta())

        assert entry["status"] == "pass"
        assert entry["mean_recall_at_10"] == 1.0


class TestRankingPublisher:
    def _latest(self, provenance_record: Any = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "benchmark": "ranking_quality",
            "gold_set": "v1",
            "timestamp": "2026-11-12T00:00:00+00:00",
            "query_count": 20,
            "memory_count": 51,
            "metrics": {"precision_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0},
        }
        if provenance_record is not None:
            payload["provenance"] = provenance_record
        return payload

    def _gate(self) -> dict[str, Any]:
        return {"status": "pass", "checks": []}

    def _meta(self) -> QualityRunMeta:
        return QualityRunMeta(
            sha="0123456789abcdef0123456789abcdef01234567",
            branch="main",
            run_number=7,
            run_url="https://example.invalid/actions/runs/7",
        )

    def test_the_provenance_is_published(self) -> None:
        record = _provenance()

        entry = merge_ranking_quality_entry(self._latest(record), self._gate(), self._meta())

        assert entry["provenance"] == record
        assert entry["status"] == "pass"

    def test_a_scored_artifact_without_provenance_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match="ranking-quality artifact has no provenance"):
            merge_ranking_quality_entry(self._latest(), self._gate(), self._meta())

    def test_a_block_whose_status_is_not_recorded_is_refused(self) -> None:
        # A complete-looking block labelled "unrecorded" states that the number cannot be
        # reproduced; publishing it would dress that up as evidence.
        record = _provenance(status="unrecorded")

        with pytest.raises(
            RuntimeError,
            match=r"status is 'unrecorded', expected 'recorded'.*must be reproducible",
        ):
            merge_ranking_quality_entry(self._latest(record), self._gate(), self._meta())

    def test_no_modes_field_is_published(self) -> None:
        # The mode comparison is its own artifact; nothing defines a published `modes` shape,
        # so inventing one here would publish a comparison no reader can interpret.
        latest = self._latest(_provenance())
        latest["modes"] = {"hybrid": []}

        entry = merge_ranking_quality_entry(latest, self._gate(), self._meta())

        assert "modes" not in entry

    def test_the_required_fields_are_the_schema_recorded_requirements(self) -> None:
        schema = json.loads(
            (_SCHEMA_DIR / "ranking-quality-benchmark-data.schema.json").read_text(encoding="utf-8")
        )
        then = schema["properties"]["runs"]["items"]["properties"]["provenance"]["then"]

        assert set(REQUIRED_PROVENANCE_FIELDS) == {"status", *then["required"]}


def _validator(schema_name: str) -> Any:
    jsonschema = pytest.importorskip("jsonschema", reason="schema contract tests need jsonschema")
    schema = json.loads((_SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


class TestPublishedDocument:
    def test_a_document_with_published_provenance_validates(self) -> None:
        entry = _merge_entry(_raw(), _meta())
        document = {
            "schema_version": 1,
            "benchmark": "hnsw_recall_latency",
            "runs": [entry],
        }

        errors = list(_validator("hnsw-benchmark-data.schema.json").iter_errors(document))

        assert errors == []

    def test_a_stale_run_validates(self) -> None:
        entry = _merge_entry(_raw(_provenance(corpus_hash="0" * 64)), _meta())
        document = {
            "schema_version": 1,
            "benchmark": "hnsw_recall_latency",
            "runs": [entry],
        }

        errors = list(_validator("hnsw-benchmark-data.schema.json").iter_errors(document))

        assert errors == []

    def test_a_ranking_document_with_published_provenance_validates(self) -> None:
        entry = merge_ranking_quality_entry(
            {
                "gold_set": "v1",
                "query_count": 20,
                "memory_count": 51,
                "metrics": {"precision_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0},
                "provenance": _provenance(gold_set_hash="0" * 64, gold_set_name="gold_set_v2.json"),
            },
            {"status": "pass", "checks": []},
            QualityRunMeta(
                sha="0123456789abcdef0123456789abcdef01234567",
                branch="main",
                run_number=7,
                run_url="https://example.invalid/actions/runs/7",
            ),
        )
        document = {
            "schema_version": 1,
            "benchmark": "ranking_quality",
            "runs": [entry],
        }

        errors = list(
            _validator("ranking-quality-benchmark-data.schema.json").iter_errors(document)
        )

        assert errors == []


def test_the_committed_hnsw_history_still_validates() -> None:
    # The widening is optional, so the file written before it existed must keep validating.
    path = _BENCH.parents[1] / "site" / "public" / "benchmarks" / "hnsw-benchmark-data.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    errors = list(_validator("hnsw-benchmark-data.schema.json").iter_errors(document))

    assert errors == []
