"""Validation and ClickHouse trace paths for batch extraction."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.extraction.batch import run_batch_extraction
from app.extraction.schema import BatchExtractionResult
from tests.unit.extraction_fakes import FakeProvider, JobParts, make_job, sample_turns


def test_duplicate_turn_index_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate turn_index"):
        BatchExtractionResult.model_validate(
            {
                "turns": [
                    {"turn_index": 1, "memories": []},
                    {"turn_index": 1, "memories": []},
                ]
            }
        )


def test_provider_duplicate_indexes_rejected() -> None:
    job = make_job(
        JobParts(
            turns=sample_turns(1),
            provider=FakeProvider(
                raw_json=json.dumps(
                    {
                        "turns": [
                            {"turn_index": 0, "memories": []},
                            {"turn_index": 0, "memories": []},
                        ]
                    }
                )
            ),
        )
    )
    with pytest.raises(ValidationError, match="duplicate turn_index"):
        run_batch_extraction(job)


@pytest.mark.parametrize("size", [1, 10, 50])
def test_missing_turn_index_rejected(size: int) -> None:
    indexes = list(range(size))
    override = [] if size == 1 else indexes[:-1]
    job = make_job(
        JobParts(turns=sample_turns(size), provider=FakeProvider(override_indexes=override))
    )
    with pytest.raises(ValueError, match="turn_index set"):
        run_batch_extraction(job)


@pytest.mark.parametrize("size", [1, 10, 50])
def test_surplus_turn_index_rejected(size: int) -> None:
    override = list(range(size)) + [size + 99]
    job = make_job(
        JobParts(turns=sample_turns(size), provider=FakeProvider(override_indexes=override))
    )
    with pytest.raises(ValueError, match="turn_index set"):
        run_batch_extraction(job)


def test_parse_failure_records_fail_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[object] = []

    def fake_insert(*, dsn, row, client=None):
        del dsn, client
        rows.append(row)
        return True

    monkeypatch.setattr("app.extraction.batch.insert_extraction_trace", fake_insert)
    job = make_job(
        JobParts(
            provider=FakeProvider(raw_json="not-json"),
            clickhouse_dsn="clickhouse://default:@localhost:8123/ibex",
        )
    )
    with pytest.raises(ValidationError):
        run_batch_extraction(job)
    assert len(rows) == 1
    assert rows[0].is_complete is False  # type: ignore[attr-defined]
    assert rows[0].error_code  # type: ignore[attr-defined]


def test_clickhouse_error_does_not_mask_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*, dsn, row, client=None):
        del dsn, row, client
        raise RuntimeError("clickhouse down")

    monkeypatch.setattr("app.extraction.batch.insert_extraction_trace", boom)
    job = make_job(JobParts(provider=FakeProvider(raw_json="{")))
    with pytest.raises(ValidationError):
        run_batch_extraction(job)
