"""Expanded org-deletion saga unit tests (edge cases + hard fails)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import org_deletion


@pytest.mark.asyncio
async def test_receipt_verified_refuses_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(org_deletion, "NON_ERASABLE_STORES", frozenset({"billing"}))
    with pytest.raises(ValueError, match="non-erasable"):
        await org_deletion._receipt_verified(AsyncMock(), "j", "billing")


@pytest.mark.asyncio
async def test_upsert_receipt_refuses_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(org_deletion, "NON_ERASABLE_STORES", frozenset({"billing"}))
    with pytest.raises(ValueError, match="non-erasable"):
        await org_deletion._upsert_receipt(
            AsyncMock(), job_id="j", store="billing", status="verified"
        )


@pytest.mark.asyncio
async def test_all_receipts_verified_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def verified(_s, _j, store):
        return store == "postgres"

    monkeypatch.setattr(org_deletion, "_receipt_verified", verified)
    assert await org_deletion._all_receipts_verified(AsyncMock(), "j") is False


@pytest.mark.asyncio
async def test_stage_clickhouse_empty_dsn_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_CLICKHOUSE_DSN", raising=False)
    settings = MagicMock(clickhouse_dsn=None)
    await org_deletion._stage_clickhouse(settings, org_id="00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_stage_objectstore_skips_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    settings = MagicMock(s3_endpoint=None)
    await org_deletion._stage_objectstore(settings, org_id="o", uris=[])


@pytest.mark.asyncio
async def test_stage_redis_scan_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncMock()

    async def scan(*, cursor=0, match=None, count=200):
        del match, count
        if cursor == 0:
            return 0, ["k1", "k2"]
        return 0, []

    client.scan = AsyncMock(side_effect=scan)
    client.delete = AsyncMock()
    client.aclose = AsyncMock()

    class _Redis:
        @staticmethod
        def from_url(*_a, **_k):
            return client

    monkeypatch.setattr("redis.asyncio.Redis", _Redis)
    settings = MagicMock(redis_url="redis://localhost/0")
    await org_deletion._stage_redis(settings, org_id="org-1")
    assert client.delete.await_count >= 1
    assert client.aclose.await_count == 1

@pytest.mark.asyncio
async def test_receipt_digests_stable() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("postgres", "verified", "t", ""),
                    ("redis", "verified", "t", ""),
                ]
            )
        )
    )
    digests = await org_deletion._receipt_digests(session, "j")
    assert "postgres" in digests
    assert len(digests["postgres"]) == 64


@pytest.mark.asyncio
async def test_incomplete_receipts_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        if "deleted_at IS NOT NULL" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    session.execute = AsyncMock(side_effect=execute)
    settings = MagicMock(database_url="postgresql+asyncpg://u:p@localhost/db", redis_url=None)
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(org_deletion, "create_engine", lambda _s: engine)
    monkeypatch.setattr(org_deletion, "create_session_factory", lambda _e: MagicMock())

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(org_deletion, "session_as_service_account", lambda _f: _CM())
    monkeypatch.setattr(org_deletion, "_collect_archived_uris", AsyncMock(return_value=[]))
    monkeypatch.setattr(org_deletion, "_stage_postgres", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_clickhouse", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_redis", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_objectstore", AsyncMock())
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", AsyncMock())
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    monkeypatch.setattr(org_deletion, "_receipt_digests", AsyncMock(return_value={}))
    monkeypatch.setattr(org_deletion, "_receipt_verified", AsyncMock(return_value=False))
    monkeypatch.setattr(org_deletion, "_upsert_receipt", AsyncMock())
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=False))

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "failed"


@pytest.mark.asyncio
async def test_skip_verified_store_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        if "deleted_at IS NOT NULL" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    settings = MagicMock(database_url="postgresql+asyncpg://u:p@localhost/db", redis_url=None)
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(org_deletion, "create_engine", lambda _s: engine)
    monkeypatch.setattr(org_deletion, "create_session_factory", lambda _e: MagicMock())

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(org_deletion, "session_as_service_account", lambda _f: _CM())
    monkeypatch.setattr(org_deletion, "_collect_archived_uris", AsyncMock(return_value=[]))
    stage_pg = AsyncMock()
    monkeypatch.setattr(org_deletion, "_stage_postgres", stage_pg)
    monkeypatch.setattr(org_deletion, "_stage_clickhouse", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_redis", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_objectstore", AsyncMock())
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", AsyncMock())
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    monkeypatch.setattr(org_deletion, "_receipt_digests", AsyncMock(return_value={}))
    monkeypatch.setattr(org_deletion, "_receipt_verified", AsyncMock(return_value=True))
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=True))

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"
    stage_pg.assert_not_awaited()
