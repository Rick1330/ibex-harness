"""Unit tests for capture archive ref recording and its failure paths.

``test_capture_redaction.py`` covers task wiring and the capture modes. This
module covers the half that decides whether a memory forget can find the
archived copy afterwards: the ``archived_to`` update, the artifact-ref insert,
the payload's memory-id extraction, and the compensation that removes a blob
when the row it was archived for cannot be updated.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.tasks import capture_redaction
from app.tasks.capture_redaction import _CaptureJob, _RedactCtx

_ORG = "org-1"
_URI = "s3://ibex-sessions/org-1/capture/full/9.json"


def _ctx(*, event_id: str | None = None, session: Any | None = None) -> _RedactCtx:
    """One redaction run's session, settings and upload ledger."""
    return _RedactCtx(
        session=session or AsyncMock(),
        settings=MagicMock(),
        job=_CaptureJob(org_id=_ORG, event_id=event_id, payload={"meta": 1}),
        uploaded=[],
    )


# ---------------------------------------------------------------------------
# Task entrypoint
# ---------------------------------------------------------------------------


def test_task_entrypoint_parses_kwargs_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(job: _CaptureJob) -> dict[str, str]:
        return {"status": "skipped", "mode": job.org_id}

    monkeypatch.setattr(capture_redaction, "_run", run)
    assert capture_redaction.apply_capture_redaction.run(org_id="org-1") == {
        "status": "skipped",
        "mode": "org-1",
    }


@pytest.mark.parametrize("org_id", [None, "", 7])
def test_parse_job_requires_a_tenant(org_id: Any) -> None:
    with pytest.raises(ValueError, match="org_id is required"):
        capture_redaction._parse_job({"org_id": org_id})


@pytest.mark.asyncio
async def test_run_refuses_without_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture_redaction, "get_settings", lambda: MagicMock(database_url=None))
    with pytest.raises(ValueError, match="database_url is required"):
        await capture_redaction._run(_CaptureJob(org_id=_ORG))


# ---------------------------------------------------------------------------
# Redacted persist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_redacted_without_an_event_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    put = MagicMock()
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", put)
    ctx = _ctx()

    await capture_redaction._persist_redacted(ctx, {"meta": 1})

    ctx.session.execute.assert_not_awaited()
    put.assert_not_called()


@pytest.mark.asyncio
async def test_persist_redacted_records_the_blob_it_uploaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=_URI))
    set_archived = AsyncMock()
    monkeypatch.setattr(capture_redaction, "_set_archived_to", set_archived)
    ctx = _ctx(event_id="9")

    await capture_redaction._persist_redacted(ctx, {"meta": 1})

    assert ctx.uploaded == [_URI]
    assert ctx.session.execute.await_count == 1
    set_archived.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_redacted_propagates_a_non_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a missing store configuration is tolerated; a seal error is not."""
    monkeypatch.setattr(
        capture_redaction, "_put_archive_blob", MagicMock(side_effect=RuntimeError("seal failed"))
    )
    ctx = _ctx(event_id="9")

    with pytest.raises(RuntimeError, match="seal failed"):
        await capture_redaction._persist_redacted(ctx, {"meta": 1})
    assert ctx.uploaded == []


@pytest.mark.asyncio
async def test_persist_redacted_compensates_when_the_ref_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=_URI))
    monkeypatch.setattr(
        capture_redaction, "_set_archived_to", AsyncMock(side_effect=RuntimeError("no row"))
    )
    monkeypatch.setattr(
        capture_redaction, "_compensate_upload", lambda uri, _org, _s: deleted.append(uri)
    )
    ctx = _ctx(event_id="9")

    with pytest.raises(RuntimeError, match="no row"):
        await capture_redaction._persist_redacted(ctx, {"meta": 1})

    assert deleted == [_URI]
    assert ctx.uploaded == []


# ---------------------------------------------------------------------------
# Full archive without an event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_payload_without_an_event_stops_after_the_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=_URI))
    set_archived = AsyncMock()
    monkeypatch.setattr(capture_redaction, "_set_archived_to", set_archived)
    ctx = _ctx()

    await capture_redaction._archive_payload(ctx, {"content": "x"})

    assert ctx.uploaded == [_URI]
    set_archived.assert_not_awaited()


# ---------------------------------------------------------------------------
# archived_to update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_archived_to_refuses_an_update_that_matched_nothing() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    job = _CaptureJob(org_id=_ORG, event_id="9")

    with pytest.raises(RuntimeError, match="matched 0 rows"):
        await capture_redaction._set_archived_to(session, job, _URI, {"memory_id": str(uuid4())})


@pytest.mark.asyncio
async def test_set_archived_to_records_one_ref_per_memory() -> None:
    memory_id = str(uuid4())
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    job = _CaptureJob(org_id=_ORG, event_id="9")

    await capture_redaction._set_archived_to(session, job, _URI, {"memory_ids": [memory_id]})

    assert session.execute.await_count == 2
    statement, params = session.execute.await_args_list[1].args
    assert "memory_artifact_refs" in str(statement)
    assert params == {
        "org_id": _ORG,
        "event_id": 9,
        "event_id_text": "9",
        "uri": _URI,
        "memory_ids": json.dumps([memory_id]),
    }


# ---------------------------------------------------------------------------
# Memory ids carried by the payload
# ---------------------------------------------------------------------------


def test_memory_ids_is_empty_without_a_payload() -> None:
    assert capture_redaction._memory_ids(None) == []
    assert capture_redaction._memory_ids({}) == []


def test_memory_ids_reads_both_capture_shapes_and_dedupes() -> None:
    first, second = str(uuid4()), str(uuid4())
    payload = {"memory_ids": [first, second, first], "memory_id": second}
    assert capture_redaction._memory_ids(payload) == [first, second]


def test_memory_ids_drops_unusable_values_without_logging_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    good = str(uuid4())
    payload = {"memory_ids": [good, "not-a-uuid", 7], "memory_id": None}

    with caplog.at_level(logging.WARNING, logger=capture_redaction.__name__):
        assert capture_redaction._memory_ids(payload) == [good]

    assert "2 unusable memory id value(s)" in caplog.text
    assert "not-a-uuid" not in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000001"),
        (UUID(int=1), "00000000-0000-0000-0000-000000000001"),
        ("NOT-A-UUID", None),
        (True, None),
        (17, None),
        (None, None),
    ],
)
def test_canonical_memory_id_accepts_only_uuids(value: Any, expected: str | None) -> None:
    assert capture_redaction._canonical_memory_id(value) == expected


# ---------------------------------------------------------------------------
# Upload compensation
# ---------------------------------------------------------------------------


def test_compensate_upload_deletes_the_archived_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import objectstore_client

    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        objectstore_client,
        "delete_uri",
        lambda uri, *, org_id, settings=None: deleted.append((uri, org_id)),
    )

    capture_redaction._compensate_upload(_URI, _ORG, MagicMock())

    assert deleted == [(_URI, _ORG)]


def test_compensate_upload_never_masks_the_original_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app import objectstore_client

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("s3 down")

    monkeypatch.setattr(objectstore_client, "delete_uri", boom)

    with caplog.at_level(logging.ERROR, logger=capture_redaction.__name__):
        capture_redaction._compensate_upload(_URI, _ORG, MagicMock())

    assert "failed to compensate archive upload" in caplog.text
