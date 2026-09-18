"""Unit tests for org deletion saga helpers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import org_deletion


@pytest.mark.asyncio
async def test_claim_job_returns_false_when_missing() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    claimed = await org_deletion._claim_job(session, job_id="j", org_id="o")
    assert claimed is False


@pytest.mark.asyncio
async def test_run_delete_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock(database_url=None)
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="database_url"):
        await org_deletion._run_delete(job_id="j", org_id="o")


def _wire_delete_session(
    monkeypatch: pytest.MonkeyPatch,
    session: AsyncMock,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> None:
    settings = MagicMock(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://127.0.0.1:6379/0",
        clickhouse_dsn="http://127.0.0.1:8123",
        s3_endpoint="http://127.0.0.1:9000",
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(org_deletion, "create_engine", lambda _s: engine)
    monkeypatch.setattr(org_deletion, "create_session_factory", lambda _e: MagicMock())

    if session_factory is not None:
        monkeypatch.setattr(
            org_deletion, "session_as_service_org", lambda _f, _org: session_factory()
        )
        return

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(org_deletion, "session_as_service_org", lambda _f, _org: _CM())


def _stub_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(org_deletion, "_stage_postgres", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_clickhouse", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_redis", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_objectstore", AsyncMock())
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", AsyncMock())
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    monkeypatch.setattr(org_deletion, "_resolve_archived_uris", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        org_deletion,
        "_receipt_digests",
        AsyncMock(
            return_value={"postgres": "a", "clickhouse": "b", "redis": "c", "objectstore": "d"}
        ),
    )


@pytest.mark.asyncio
async def test_run_delete_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "status IN ('pending', 'failed')" in sql or "status = 'pending'" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    _wire_delete_session(monkeypatch, session)
    _stub_stages(monkeypatch)
    states: dict[str, bool] = {s: False for s in org_deletion._STORES}

    async def receipt_verified(_s, job_id, store):
        del job_id
        return states[store]

    async def upsert(_s, receipt):
        if receipt.status == "verified":
            states[receipt.store] = True

    async def all_verified(_s, job_id):
        del job_id
        return all(states.values())

    monkeypatch.setattr(org_deletion, "_receipt_verified", receipt_verified)
    monkeypatch.setattr(org_deletion, "_upsert_receipt", upsert)
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", all_verified)

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"
    org_deletion._stage_postgres.assert_awaited()  # type: ignore[attr-defined]
    org_deletion._publish_model_policy_invalidate.assert_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hold_gate_blocks_deletion(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    _wire_delete_session(monkeypatch, session)
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "hold_blocked"


@pytest.mark.asyncio
async def test_run_delete_cascade_failure_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    fail_session = AsyncMock()
    fail_session.execute = AsyncMock()
    sessions = iter([session, fail_session])

    class _CM:
        def __init__(self):
            self._session = next(sessions)

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            return None

    _wire_delete_session(monkeypatch, session, session_factory=_CM)
    monkeypatch.setattr(org_deletion, "_resolve_archived_uris", AsyncMock(return_value=[]))
    monkeypatch.setattr(org_deletion, "_receipt_verified", AsyncMock(return_value=False))
    monkeypatch.setattr(
        org_deletion, "_stage_postgres", AsyncMock(side_effect=RuntimeError("cascade boom"))
    )
    inv = AsyncMock()
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", inv)
    with pytest.raises(RuntimeError, match="cascade boom"):
        await org_deletion._run_delete(job_id="j", org_id="o")
    assert fail_session.execute.await_count == 1
    inv.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_postgres_commit_failure_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Commit-on-exit errors must mark the job failed (reclaimable), not leave running."""
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    fail_session = AsyncMock()
    fail_session.execute = AsyncMock()
    # 1) postgres purge txn  2) optional-stores txn (commit fails)  3) fail marker
    call_n = {"n": 0}

    class _CM:
        def __init__(self):
            call_n["n"] += 1
            self._n = call_n["n"]

        async def __aenter__(self):
            if self._n == 3:
                return fail_session
            return session

        async def __aexit__(self, *args):
            if self._n == 2:
                raise RuntimeError("commit failed")

    _wire_delete_session(monkeypatch, session, session_factory=_CM)
    _stub_stages(monkeypatch)
    monkeypatch.setattr(org_deletion, "_receipt_verified", AsyncMock(return_value=False))
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=True))

    async def upsert(_s, receipt):
        del receipt

    monkeypatch.setattr(org_deletion, "_upsert_receipt", upsert)

    with pytest.raises(RuntimeError, match="commit failed"):
        await org_deletion._run_delete(job_id="j", org_id="o")
    assert fail_session.execute.await_count == 1


def test_cascade_includes_soft_delete_org() -> None:
    joined = "\n".join(org_deletion._CASCADE_STATEMENTS)
    assert "deleted_at" in joined
    assert "memory_feedback" in joined
    assert "organization_invites" in joined
    assert "session_turns" not in joined
    pre = "\n".join(org_deletion._PG_PRE_CASCADE)
    assert "evidence_outbox" in pre
    assert "org_model_policies" in pre


def test_task_time_limits() -> None:
    task = org_deletion.delete_organization
    assert task.soft_time_limit == 300
    assert task.time_limit == 600


def test_non_erasable_allowlist_empty() -> None:
    assert len(org_deletion.NON_ERASABLE_STORES) == 0


@pytest.mark.asyncio
async def test_run_delete_still_runs_stages_when_org_already_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Soft-deleted orgs must still execute store stages — never invent receipts."""
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    _wire_delete_session(monkeypatch, session)
    _stub_stages(monkeypatch)
    states: dict[str, bool] = {s: False for s in org_deletion._STORES}

    async def receipt_verified(_s, job_id, store):
        del job_id
        return states[store]

    async def upsert(_s, receipt):
        if receipt.status == "verified":
            states[receipt.store] = True

    monkeypatch.setattr(org_deletion, "_receipt_verified", receipt_verified)
    monkeypatch.setattr(org_deletion, "_upsert_receipt", upsert)
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=True))

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"
    org_deletion._stage_postgres.assert_awaited()  # type: ignore[attr-defined]
    org_deletion._stage_clickhouse.assert_awaited()  # type: ignore[attr-defined]
    org_deletion._stage_redis.assert_awaited()  # type: ignore[attr-defined]
    org_deletion._stage_objectstore.assert_awaited()  # type: ignore[attr-defined]
    assert not hasattr(org_deletion, "_ensure_all_receipts_verified")


@pytest.mark.asyncio
async def test_resolve_archived_uris_reuses_snapshot() -> None:
    """After Postgres purge, retries must reuse the persisted URI snapshot."""
    session = AsyncMock()
    uris = ["s3://bucket/archives/outside-prefix.json"]
    session.execute = AsyncMock(
        return_value=MagicMock(first=MagicMock(return_value=(uris,)))
    )
    out = await org_deletion._resolve_archived_uris(session, job_id="j", org_id="o")
    assert out == uris
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_resolve_archived_uris_collects_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(first=MagicMock(return_value=(None,))),  # no snapshot
            MagicMock(),  # save
        ]
    )
    monkeypatch.setattr(
        org_deletion,
        "_collect_archived_uris",
        AsyncMock(return_value=["s3://b/x", "s3://b/y"]),
    )
    out = await org_deletion._resolve_archived_uris(session, job_id="j", org_id="o")
    assert out == ["s3://b/x", "s3://b/y"]
    assert session.execute.await_count == 2
    save_params = session.execute.await_args_list[1].args[1]
    assert '"s3://b/x"' in save_params["uris"]


@pytest.mark.asyncio
async def test_retry_passes_snapshot_uris_to_objectstore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-postgres retry must forward snapshot URIs even when collect would be empty."""
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    _wire_delete_session(monkeypatch, session)
    _stub_stages(monkeypatch)
    snapshot = ["s3://other-bucket/org-archives/blob.bin"]
    monkeypatch.setattr(
        org_deletion, "_resolve_archived_uris", AsyncMock(return_value=snapshot)
    )
    # Postgres already verified — collect would be empty after purge.
    monkeypatch.setattr(
        org_deletion,
        "_receipt_verified",
        AsyncMock(side_effect=lambda _s, _j, store: store == "postgres"),
    )
    monkeypatch.setattr(org_deletion, "_upsert_receipt", AsyncMock())
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=True))

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"
    org_deletion._stage_postgres.assert_not_awaited()  # type: ignore[attr-defined]
    org_deletion._stage_objectstore.assert_awaited_once()  # type: ignore[attr-defined]
    kwargs = org_deletion._stage_objectstore.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["uris"] == snapshot


def test_claim_job_sql_allows_failed_retry() -> None:
    src = inspect.getsource(org_deletion._claim_job)
    assert "status IN ('pending', 'failed')" in " ".join(src.split())
    assert "status IN ('pending', 'failed', 'hold_blocked')" not in " ".join(src.split())


def test_ch_queries_are_literal_mapping() -> None:
    src_delete = inspect.getsource(org_deletion)
    for table in org_deletion._CH_TABLES:
        assert table in org_deletion._CH_DELETE_QUERIES
        assert table in org_deletion._CH_COUNT_QUERIES
        q = org_deletion._CH_DELETE_QUERIES[table]
        assert "f-string" not in q
        assert table in q
        # Binding uses param_org_id, not an interpolated identifier.
        assert "{org_id:UUID}" in q
    assert "_CH_DELETE_QUERIES" in src_delete
    assert "f\"ALTER TABLE" not in src_delete
    assert "f'ALTER TABLE" not in src_delete
