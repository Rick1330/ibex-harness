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


def _stub_upload(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub the blob upload and return the archived_to mock the caller asserts on."""
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=_URI))
    set_archived = AsyncMock()
    monkeypatch.setattr(capture_redaction, "_set_archived_to", set_archived)
    return set_archived


@pytest.mark.asyncio
async def test_persist_redacted_records_the_blob_it_uploaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_archived = _stub_upload(monkeypatch)
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
# Provenance without a complete address
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_redacted_without_a_memory_id_skips_the_object_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_archived = _stub_upload(monkeypatch)
    ctx = _ctx(event_id="9")

    await capture_redaction._persist_redacted(ctx, {"meta": 1})

    assert ctx.uploaded == [_URI]
    assert ctx.session.execute.await_count == 1
    set_archived.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_redacted_records_the_object_ref_after_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_archived = _stub_upload(monkeypatch)
    memory_id = str(uuid4())
    ctx = _ctx(event_id="9")

    await capture_redaction._persist_redacted(ctx, {"memory_id": memory_id})

    assert ctx.uploaded == [_URI]
    # data update, session-event ref, then the object ref; archived_to is stubbed
    assert ctx.session.execute.await_count == 3
    object_ref = ctx.session.execute.await_args_list[2].args[1]
    assert object_ref["uri"] == _URI
    assert json.loads(object_ref["memory_ids"]) == [memory_id]
    set_archived.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_redacted_records_the_event_ref_when_s3_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handled configuration error must not lose the erasure address."""
    memory_id = str(uuid4())
    monkeypatch.setattr(
        capture_redaction,
        "_put_archive_blob",
        MagicMock(side_effect=RuntimeError("S3_ENDPOINT unset")),
    )
    ctx = _ctx(event_id="9")

    await capture_redaction._persist_redacted(ctx, {"memory_id": memory_id})

    assert ctx.uploaded == []
    assert ctx.session.execute.await_count == 2
    statement, params = ctx.session.execute.await_args_list[1].args
    assert "memory_artifact_refs" in str(statement)
    assert params["event_id"] == 9
    assert params["uri"] is None


@pytest.mark.asyncio
async def test_record_artifact_refs_does_nothing_without_an_address() -> None:
    session = AsyncMock()

    await capture_redaction._record_artifact_refs(
        session,
        capture_redaction._ArtifactRefs(
            org_id=_ORG,
            memory_ids=(str(uuid4()),),
        ),
    )

    session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# Full archive without an event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_payload_without_an_event_skips_the_event_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_archived = _stub_upload(monkeypatch)
    ctx = _ctx()

    await capture_redaction._archive_payload(ctx, {"content": "x"})

    assert ctx.uploaded == [_URI]
    set_archived.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_payload_without_an_event_records_the_object_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full capture with a memory id but no event id must still be findable."""
    _stub_upload(monkeypatch)
    ctx = _ctx()
    memory_id = str(uuid4())

    await capture_redaction._archive_payload(ctx, {"memory_id": memory_id})

    assert ctx.uploaded == [_URI]
    ctx.session.execute.assert_awaited_once()
    statement, params = ctx.session.execute.await_args_list[0].args
    assert "memory_artifact_refs" in str(statement)
    assert params["event_id"] is None
    assert params["uri"] == _URI
    assert json.loads(params["memory_ids"]) == [memory_id]


# ---------------------------------------------------------------------------
# archived_to update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_archived_to_refuses_an_update_that_matched_nothing() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    job = _CaptureJob(org_id=_ORG, event_id="9")

    with pytest.raises(RuntimeError, match="matched 0 rows"):
        await capture_redaction._set_archived_to(session, job, _URI)


@pytest.mark.asyncio
async def test_set_archived_to_updates_only_the_event_row() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    job = _CaptureJob(org_id=_ORG, event_id="9")

    await capture_redaction._set_archived_to(session, job, _URI)

    assert session.execute.await_count == 1
    statement, params = session.execute.await_args_list[0].args
    assert "archived_to" in str(statement)
    assert params == {"event_id": 9, "org_id": _ORG, "uri": _URI}


@pytest.mark.asyncio
async def test_record_artifact_refs_writes_the_object_and_event_halves() -> None:
    memory_id = str(uuid4())
    session = AsyncMock()

    await capture_redaction._record_artifact_refs(
        session,
        capture_redaction._ArtifactRefs(
            org_id=_ORG,
            memory_ids=(memory_id,),
            event_id=9,
            uri=_URI,
        ),
    )

    statement, params = session.execute.await_args_list[0].args
    assert "memory_artifact_refs" in str(statement)
    assert params == {
        "org_id": _ORG,
        "event_id": 9,
        "event_id_text": "9",
        "uri": _URI,
        "memory_ids": json.dumps([memory_id]),
    }


@pytest.mark.asyncio
async def test_record_artifact_refs_records_the_object_without_an_event() -> None:
    """A full capture with a memory id but no event id is still reachable."""
    memory_id = str(uuid4())
    session = AsyncMock()

    await capture_redaction._record_artifact_refs(
        session,
        capture_redaction._ArtifactRefs(
            org_id=_ORG,
            memory_ids=(memory_id,),
            event_id=None,
            uri=_URI,
        ),
    )

    _, params = session.execute.await_args_list[0].args
    assert params["event_id"] is None
    assert params["event_id_text"] is None
    assert params["uri"] == _URI


@pytest.mark.asyncio
async def test_record_artifact_refs_records_the_event_without_an_upload() -> None:
    """A capture whose S3 write is skipped still records its session-event link."""
    memory_id = str(uuid4())
    session = AsyncMock()

    await capture_redaction._record_artifact_refs(
        session,
        capture_redaction._ArtifactRefs(
            org_id=_ORG,
            memory_ids=(memory_id,),
            event_id=9,
        ),
    )

    _, params = session.execute.await_args_list[0].args
    assert params["uri"] is None
    assert params["event_id"] == 9


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
