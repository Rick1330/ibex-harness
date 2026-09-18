"""Capture redaction task unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.tasks import capture_redaction
from app.tasks.capture_redaction import _CaptureJob


@pytest.mark.asyncio
async def test_resolve_capture_mode_defaults_metadata_only() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    mode = await capture_redaction.resolve_capture_mode(session, org_id="o", agent_id=None)
    assert mode == "metadata_only"


@pytest.mark.asyncio
async def test_resolve_capture_mode_uses_row() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=("full",))))
    mode = await capture_redaction.resolve_capture_mode(session, org_id="o", agent_id=None)
    assert mode == "full"


def test_task_limits() -> None:
    assert capture_redaction.apply_capture_redaction.soft_time_limit == 120
    assert capture_redaction.apply_capture_redaction.time_limit == 180


def _wire_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    session: AsyncMock | None = None,
) -> AsyncMock:
    settings = MagicMock(database_url="postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setattr(capture_redaction, "get_settings", lambda: settings)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(capture_redaction, "create_engine", lambda _s: engine)
    monkeypatch.setattr(capture_redaction, "create_session_factory", lambda _e: MagicMock())
    sess = session or AsyncMock()
    sess.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))

    class _CM:
        async def __aenter__(self):
            return sess

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(capture_redaction, "session_as_service_org", lambda _f, _org: _CM())
    monkeypatch.setattr(
        capture_redaction,
        "resolve_capture_mode",
        AsyncMock(return_value=mode),
    )
    return sess


@pytest.mark.asyncio
async def test_run_none_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_run(monkeypatch, mode="none")
    out = await capture_redaction._run(_CaptureJob(org_id="o"))
    assert out == {"status": "skipped", "mode": "none"}


@pytest.mark.asyncio
async def test_run_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_run(monkeypatch, mode="metadata_only")
    out = await capture_redaction._run(_CaptureJob(org_id="o", event_id="1", payload={"a": 1}))
    assert out == {"status": "redacted", "mode": "metadata_only"}


@pytest.mark.asyncio
async def test_run_redacted_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _wire_run(monkeypatch, mode="redacted")
    monkeypatch.setattr(
        capture_redaction,
        "_put_archive_blob",
        MagicMock(side_effect=RuntimeError("S3_ENDPOINT unset")),
    )
    out = await capture_redaction._run(
        _CaptureJob(
            org_id="o",
            event_id="42",
            agent_id=str(uuid4()),
            payload={"raw": "x", "meta": "y"},
        )
    )
    assert out["status"] == "redacted"
    assert out["mode"] == "redacted"
    assert out["event_id"] == "42"
    assert sess.execute.await_count >= 1
    call_args = sess.execute.await_args_list[0]
    params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("params")
    assert '"raw"' not in params["data"]
    assert "meta" in params["data"]


@pytest.mark.asyncio
async def test_run_full_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _wire_run(monkeypatch, mode="full")
    monkeypatch.setattr(
        capture_redaction,
        "_put_archive_blob",
        MagicMock(return_value="s3://ibex-sessions/o/capture/full/1.json"),
    )
    out = await capture_redaction._run(
        _CaptureJob(org_id="o", event_id="1", payload={"content": "secret"})
    )
    assert out["status"] == "archived"
    assert out["mode"] == "full"
    assert sess.execute.await_count >= 1


@pytest.mark.asyncio
async def test_run_full_archive_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_run(monkeypatch, mode="full")
    monkeypatch.setattr(
        capture_redaction,
        "_put_archive_blob",
        MagicMock(side_effect=RuntimeError("seal failed")),
    )
    job = _CaptureJob(org_id="o", event_id="1", payload={"content": "secret"})
    with pytest.raises(RuntimeError, match="seal failed"):
        await capture_redaction._run(job)


def test_parse_job_from_kwargs() -> None:
    job = capture_redaction._parse_job({"org_id": "o", "event_id": "1", "payload": {"a": 1}})
    assert job.org_id == "o"
    assert job.event_id == "1"
    assert job.payload == {"a": 1}


def test_parse_job_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="payload must be an object"):
        capture_redaction._parse_job({"org_id": "o", "payload": ["not", "object"]})


def test_put_archive_blob_unique_key_without_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    keys: list[str] = []

    def fake_put(key: str, body: bytes, *, settings=None):
        del body, settings
        keys.append(key)
        return f"s3://ibex-sessions/{key}"

    monkeypatch.setattr("app.objectstore_client.put_encrypted_json", fake_put)
    settings = MagicMock()
    job = _CaptureJob(org_id="org-1", payload={"a": 1})
    capture_redaction._put_archive_blob(settings, job, {"a": 1}, "full")
    capture_redaction._put_archive_blob(settings, job, {"a": 1}, "full")
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert keys[0].startswith("org-1/capture/full/")
    assert not keys[0].endswith("/anon.json")


@pytest.mark.asyncio
async def test_archive_compensates_when_set_archived_to_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sess = _wire_run(monkeypatch, mode="full")
    uri = "s3://ibex-sessions/o/capture/full/1.json"
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=uri))
    deleted: list[str] = []

    async def boom(*_a, **_k):
        raise RuntimeError("db update failed")

    monkeypatch.setattr(capture_redaction, "_set_archived_to", boom)
    monkeypatch.setattr(
        capture_redaction,
        "_compensate_upload",
        lambda u, _s: deleted.append(u),
    )
    job = _CaptureJob(org_id="o", event_id="1", payload={"content": "secret"})
    with pytest.raises(RuntimeError, match="db update failed"):
        await capture_redaction._run(job)
    assert deleted == [uri]
    assert sess.execute.await_count >= 0


@pytest.mark.asyncio
async def test_archive_compensates_when_session_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outer _run deletes uploaded blobs if the service-org transaction aborts."""
    settings = MagicMock(database_url="postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setattr(capture_redaction, "get_settings", lambda: settings)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(capture_redaction, "create_engine", lambda _s: engine)
    monkeypatch.setattr(capture_redaction, "create_session_factory", lambda _e: MagicMock())
    sess = AsyncMock()
    uri = "s3://ibex-sessions/o/capture/full/1.json"
    deleted: list[str] = []

    class _BoomCM:
        async def __aenter__(self):
            return sess

        async def __aexit__(self, *args):
            raise RuntimeError("commit failed")

    monkeypatch.setattr(capture_redaction, "session_as_service_org", lambda _f, _org: _BoomCM())
    monkeypatch.setattr(
        capture_redaction, "resolve_capture_mode", AsyncMock(return_value="full")
    )
    monkeypatch.setattr(capture_redaction, "_put_archive_blob", MagicMock(return_value=uri))
    monkeypatch.setattr(capture_redaction, "_set_archived_to", AsyncMock())
    monkeypatch.setattr(
        capture_redaction,
        "_compensate_upload",
        lambda u, _s: deleted.append(u),
    )

    job = _CaptureJob(org_id="o", event_id="1", payload={"content": "x"})
    with pytest.raises(RuntimeError, match="commit failed"):
        await capture_redaction._run(job)
    assert deleted == [uri]

