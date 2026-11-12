"""Tests for publishing a run's provenance: required on the way in, restated on the way out.

Two publishers consume the raw artifacts: ``build_published_data`` for HNSW recall/latency and
``publish_quality_common.merge_ranking_quality_entry`` for ranking quality. Both must refuse a raw
artifact that cannot say what produced it, and the HNSW one must not claim an older corpus is the
current one. Neither schema makes the block required -- that is what keeps historical files
valid -- so the rule lives in the publishers and is tested here.
"""

from __future__ import annotations

import json
import re
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
    RANKING_PROVENANCE_FIELDS,
    REQUIRED_PROVENANCE_FIELDS,
    merge_ranking_quality_entry,
    permitted_provenance_fields,
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
    "corpus_status": "current",
    "dirty": False,
}
# The two publishers measure different corpora, and the schemas require different identity
# fields for them: the ranking schema also needs the gold set, because there the gold set is the
# corpus. The fixtures therefore start from the corpus each publisher actually measures, and the
# identity fields (`corpus_hash`, `corpus_manifest`) are read from the checkout: a fixture that
# hard-coded them would pass a restatement nobody can re-derive.


def _provenance(**overrides: Any) -> dict[str, Any]:
    """A complete recorded block for the HNSW corpus in this checkout."""
    corpus_hash, manifest = provenance.corpus_identity("hnsw")
    record = dict(_RECORDED, corpus_hash=corpus_hash, corpus_manifest=manifest)
    record.update(overrides)
    return record


def _gold_provenance(**overrides: Any) -> dict[str, Any]:
    """A complete recorded block for the v1 gold corpus in this checkout."""
    corpus_hash, manifest = provenance.corpus_identity("gold_v1")
    record = _provenance(
        corpus_hash=corpus_hash,
        corpus_manifest=manifest,
        gold_set_hash=corpus_hash,
        gold_set_name="gold_set_v1.json",
    )
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


def _recorded_requirements(schema_name: str) -> set[str]:
    """The fields a schema requires of a ``status == "recorded"`` provenance block."""
    schema = json.loads((_SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    then = schema["properties"]["runs"]["items"]["properties"]["provenance"]["then"]
    return {"status", *then["required"]}


def _declared_keys(schema_name: str) -> set[str]:
    """Every provenance key a schema declares, which is every key it will accept."""
    schema = json.loads((_SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    return set(schema["properties"]["runs"]["items"]["properties"]["provenance"]["properties"])


class TestHnswPublisher:
    def test_the_raw_provenance_is_published(self) -> None:
        record = _provenance()

        entry = _merge_entry(_raw(record), _meta())

        assert entry["provenance"] == record

    def test_a_run_measured_on_a_modified_tree_is_refused(self) -> None:
        # `dirty` is written by the one fail-closed implementation, so `true` means the code that
        # produced the number may not be the code the sha names. The offline checker refuses the
        # same flag, so publishing it would write a claim the project's own gate rejects.
        raw = _raw(_provenance(dirty=True))
        meta = _meta()

        with pytest.raises(
            RuntimeError,
            match=(
                "dirty is true; a run measured on a modified tree cannot be reproduced from its"
                " commit; re-run the bench on a clean checkout"
            ),
        ):
            _merge_entry(raw, meta)

    def test_a_raw_artifact_without_provenance_is_refused(self) -> None:
        raw = _raw(include=False)
        meta = _meta()

        with pytest.raises(RuntimeError, match="raw artifact has no provenance; re-run the bench"):
            _merge_entry(raw, meta)

    def test_an_empty_provenance_block_is_refused(self) -> None:
        raw = _raw({})
        meta = _meta()

        with pytest.raises(RuntimeError, match="has no provenance"):
            _merge_entry(raw, meta)

    def test_an_incomplete_provenance_block_is_refused(self) -> None:
        # A half-written block would publish a corpus hash next to no runner identity, which
        # reads as a reproducible measurement when it is not one.
        record = _provenance()
        del record["runner_ram_mib"]
        raw = _raw(record)
        meta = _meta()

        with pytest.raises(RuntimeError, match="incomplete \\(missing runner_ram_mib\\)"):
            _merge_entry(raw, meta)

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
        # The one rule a reader can re-derive: current exactly when the recorded identity is the
        # corpus here. A run that recorded "stale" before its corpus was committed is published
        # as current, because the bytes it hashed are the bytes in this checkout; the run's own
        # `dirty` flag still records the state of the tree it was measured on.
        entry = _merge_entry(_raw(_provenance(corpus_status="stale")), _meta())

        assert entry["provenance"]["corpus_status"] == "current"
        assert entry["provenance"]["dirty"] is False

    def test_a_matching_hash_under_a_different_manifest_is_published_as_stale(self) -> None:
        # The hash alone is not the corpus: the manifest states what the hash covers, and the
        # offline checker compares both. Restating "current" from the hash would write a claim the
        # project's own checker refuses.
        record = _provenance(corpus_manifest="pgvector|synth.py=x|corpus.py=y|dim=1024,active=64")

        entry = _merge_entry(_raw(record), _meta())

        assert entry["provenance"]["corpus_status"] == "stale"

    def test_the_published_entry_still_carries_the_gate_result(self) -> None:
        entry = _merge_entry(_raw(), _meta())

        assert entry["status"] == "pass"
        assert entry["mean_recall_at_10"] == 1.0

    def test_a_run_on_a_locally_modified_corpus_is_published_as_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The hash is the one this checkout computes, but the corpus file is modified, so the
        # bytes are not the committed ones a reader would get: the run is not current.
        monkeypatch.setattr(provenance, "corpus_status", lambda _kind: "stale")

        entry = _merge_entry(_raw(_provenance()), _meta())

        assert entry["provenance"]["corpus_status"] == "stale"


class TestProvenanceValues:
    """A checked field with an impossible value is refused, not published.

    Presence is not evidence: ``runner_cpu_count = 0``, ``corpus_hash = "bad"`` and
    ``dirty = "false"`` all fill the block while describing a run nobody can reproduce, and a
    published number nobody can reproduce is not evidence. An optional field is checked the same
    way once a record carries it, because the schema's type rules apply to it then too.
    """

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({"runner_cpu_count": 0}, "runner_cpu_count must be a positive integer"),
            ({"runner_cpu_count": True}, "runner_cpu_count must be a positive integer"),
            ({"runner_ram_mib": 0}, "runner_ram_mib must be a positive integer"),
            ({"corpus_hash": "bad"}, "corpus_hash must be 64 lowercase hex characters"),
            ({"corpus_hash": "A" * 64}, "corpus_hash must be 64 lowercase hex characters"),
            ({"corpus_manifest": 12}, "corpus_manifest must be a non-empty string"),
            ({"runner_cpu_model": ""}, "runner_cpu_model must be a non-empty string"),
            ({"corpus_hash_algo": "md5"}, "corpus_hash_algo must be 'sha256'"),
            ({"corpus_status": "unknown"}, "corpus_status must be 'current' or 'stale'"),
            ({"dirty": "false"}, "dirty must be a boolean"),
            ({"seed": "123"}, "seed must be an integer"),
            ({"seed": True}, "seed must be an integer"),
        ],
    )
    def test_an_impossible_value_is_refused(self, overrides: dict[str, Any], expected: str) -> None:
        raw = _raw(_provenance(**overrides))
        meta = _meta()

        with pytest.raises(RuntimeError, match=re.escape(expected)):
            _merge_entry(raw, meta)

    def test_a_declared_optional_field_is_published(self) -> None:
        # `seed` is declared by both schemas, so it may be written -- and an integer one is the
        # only form the schema accepts.
        entry = _merge_entry(_raw(_provenance(seed=1234)), _meta())

        assert entry["provenance"]["seed"] == 1234

    def test_an_undeclared_field_is_refused(self) -> None:
        # The schema closes the block with `additionalProperties: false`, so a publisher that
        # copied an unknown key would write a file the offline checker cannot validate.
        raw = _raw(_provenance(turbo=True))
        meta = _meta()

        with pytest.raises(RuntimeError, match="has undeclared field\\(s\\) turbo") as caught:
            _merge_entry(raw, meta)

        assert "published schema rejects a key it does not declare" in str(caught.value)

    def test_every_invalid_field_is_named_at_once(self) -> None:
        raw = _raw(_provenance(runner_cpu_count=0, dirty="false"))
        meta = _meta()

        with pytest.raises(
            RuntimeError, match="runner_cpu_count must be a positive integer"
        ) as caught:
            _merge_entry(raw, meta)

        assert "dirty must be a boolean" in str(caught.value)

    def test_an_unexpected_status_is_refused(self) -> None:
        raw = _raw(_provenance(status="partial"))
        meta = _meta()

        with pytest.raises(RuntimeError, match="provenance.status is 'partial'"):
            _merge_entry(raw, meta)


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
        record = _gold_provenance()

        entry = merge_ranking_quality_entry(self._latest(record), self._gate(), self._meta())

        assert entry["provenance"] == record
        assert entry["status"] == "pass"

    def test_a_scored_artifact_without_provenance_is_refused(self) -> None:
        latest = self._latest()
        gate = self._gate()
        meta = self._meta()

        with pytest.raises(RuntimeError, match="ranking-quality artifact has no provenance"):
            merge_ranking_quality_entry(latest, gate, meta)

    def test_a_block_whose_status_is_not_recorded_is_refused(self) -> None:
        # A complete-looking block labelled "unrecorded" states that the number cannot be
        # reproduced; publishing it would dress that up as evidence.
        latest = self._latest(_gold_provenance(status="unrecorded"))
        gate = self._gate()
        meta = self._meta()

        with pytest.raises(
            RuntimeError,
            match=r"status is 'unrecorded', expected 'recorded'.*must be reproducible",
        ):
            merge_ranking_quality_entry(latest, gate, meta)

    def test_a_recorded_block_without_the_gold_set_is_refused(self) -> None:
        # The gold set is this corpus, so a recorded run that does not name it cannot be
        # re-derived; the ranking schema requires the pair, and so does the publisher.
        latest = self._latest(_provenance())
        gate = self._gate()
        meta = self._meta()

        with pytest.raises(RuntimeError, match="missing gold_set_hash, gold_set_name"):
            merge_ranking_quality_entry(latest, gate, meta)

    def test_a_run_on_an_older_gold_set_is_published_as_stale(self) -> None:
        # Publishing an older measurement is legitimate; claiming it measured today's gold set
        # is not, so the run is published and the claim is corrected.
        record = _gold_provenance(corpus_hash="0" * 64, gold_set_hash="0" * 64)

        entry = merge_ranking_quality_entry(self._latest(record), self._gate(), self._meta())

        assert entry["provenance"]["corpus_status"] == "stale"
        assert entry["provenance"]["corpus_hash"] == "0" * 64

    def test_a_gold_set_hash_that_disagrees_with_the_corpus_is_published_as_stale(self) -> None:
        # On this benchmark the gold set is the corpus, so the offline checker refuses a record
        # that states two hashes for it. Restating "current" from `corpus_hash` alone would write
        # exactly that record.
        record = _gold_provenance(gold_set_hash="0" * 64)

        entry = merge_ranking_quality_entry(self._latest(record), self._gate(), self._meta())

        assert entry["provenance"]["corpus_status"] == "stale"

    def test_a_run_measured_on_a_modified_tree_is_refused(self) -> None:
        latest = self._latest(_gold_provenance(dirty=True))
        gate = self._gate()
        meta = self._meta()

        with pytest.raises(
            RuntimeError,
            match=(
                "dirty is true; a run measured on a modified tree cannot be reproduced from its"
                " commit; re-run the bench on a clean checkout"
            ),
        ):
            merge_ranking_quality_entry(latest, gate, meta)

    def test_a_locally_modified_gold_set_is_published_as_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(provenance, "corpus_status", lambda _kind: "stale")

        entry = merge_ranking_quality_entry(
            self._latest(_gold_provenance()), self._gate(), self._meta()
        )

        assert entry["provenance"]["corpus_status"] == "stale"

    def test_no_modes_field_is_published(self) -> None:
        # The mode comparison is its own artifact; nothing defines a published `modes` shape,
        # so inventing one here would publish a comparison no reader can interpret.
        latest = self._latest(_gold_provenance())
        latest["modes"] = {"hybrid": []}

        entry = merge_ranking_quality_entry(latest, self._gate(), self._meta())

        assert "modes" not in entry

    def test_the_publishers_require_what_the_schemas_require(self) -> None:
        assert set(REQUIRED_PROVENANCE_FIELDS) == _recorded_requirements(
            "hnsw-benchmark-data.schema.json"
        )
        assert set(RANKING_PROVENANCE_FIELDS) == _recorded_requirements(
            "ranking-quality-benchmark-data.schema.json"
        )

    def test_the_publishers_permit_exactly_what_the_schemas_declare(self) -> None:
        # The schema closes the block, so its property set is the whole of what may be written.
        # A permitted key that the schema does not declare would publish an invalid file, and a
        # declared key the publisher refuses would refuse a valid one.
        assert permitted_provenance_fields(REQUIRED_PROVENANCE_FIELDS) == _declared_keys(
            "hnsw-benchmark-data.schema.json"
        )
        assert permitted_provenance_fields(RANKING_PROVENANCE_FIELDS) == _declared_keys(
            "ranking-quality-benchmark-data.schema.json"
        )


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

    def test_a_published_optional_field_validates(self) -> None:
        # The publisher permits `seed` because the schema declares it: what one refuses, the other
        # must accept, or a valid raw run could never be published.
        entry = _merge_entry(_raw(_provenance(seed=7)), _meta())
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
                "provenance": _gold_provenance(),
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

    def test_a_recorded_ranking_block_without_the_gold_set_fails_the_schema(self) -> None:
        # The block is complete for the HNSW corpus and unusable for this one: a recorded
        # ranking run must state the gold set it measured.
        document = {
            "schema_version": 1,
            "benchmark": "ranking_quality",
            "runs": [
                {
                    "sha": "b" * 40,
                    "short_sha": "b" * 7,
                    "timestamp": "2026-11-12T00:00:00+00:00",
                    "branch": "main",
                    "run_number": 2,
                    "run_url": "https://example.invalid/actions/runs/2",
                    "gold_set": "v1",
                    "metrics": {"precision_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0},
                    "status": "pass",
                    "provenance": _provenance(),
                }
            ],
        }

        errors = [
            error.message
            for error in _validator("ranking-quality-benchmark-data.schema.json").iter_errors(
                document
            )
        ]

        assert any("gold_set_name" in message for message in errors), errors


def test_the_committed_hnsw_history_still_validates() -> None:
    # The widening is optional, so the file written before it existed must keep validating.
    path = _BENCH.parents[1] / "site" / "public" / "benchmarks" / "hnsw-benchmark-data.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    errors = list(_validator("hnsw-benchmark-data.schema.json").iter_errors(document))

    assert errors == []
