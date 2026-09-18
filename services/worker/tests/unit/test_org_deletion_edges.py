"""Expanded org-deletion saga unit tests (edge cases + hard fails)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import org_deletion


def _wire_run(monkeypatch: pytest.MonkeyPatch, session: AsyncMock) -> None:
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

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(org_deletion, "session_as_service_org", lambda _f, _org: _CM())


def _claimable_session_execute():
    """SQL side-effect: claim succeeds, no legal hold, empty otherwise."""

    async def execute(stmt, params=None):
        del params
        sql = str(stmt)
        if "pending" in sql or "failed" in sql:
            return MagicMock(first=MagicMock(return_value=(1,)))
        if "legal_holds" in sql:
            return MagicMock(first=MagicMock(return_value=None))
        return MagicMock(first=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

    return execute


def _stub_store_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt_verified: bool,
    all_verified: bool,
) -> AsyncMock | None:
    monkeypatch.setattr(org_deletion, "_resolve_archived_uris", AsyncMock(return_value=[]))
    stage_pg = AsyncMock()
    monkeypatch.setattr(org_deletion, "_stage_postgres", stage_pg)
    monkeypatch.setattr(org_deletion, "_stage_clickhouse", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_redis", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_objectstore", AsyncMock())
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", AsyncMock())
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    monkeypatch.setattr(org_deletion, "_receipt_digests", AsyncMock(return_value={}))
    monkeypatch.setattr(
        org_deletion, "_receipt_verified", AsyncMock(return_value=receipt_verified)
    )
    monkeypatch.setattr(org_deletion, "_upsert_receipt", AsyncMock())
    monkeypatch.setattr(
        org_deletion, "_all_receipts_verified", AsyncMock(return_value=all_verified)
    )
    return stage_pg


@pytest.mark.asyncio
async def test_receipt_verified_refuses_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(org_deletion, "NON_ERASABLE_STORES", frozenset({"billing"}))
    session = AsyncMock()
    call = org_deletion._receipt_verified(session, "j", "billing")
    with pytest.raises(ValueError, match="non-erasable"):
        await call


@pytest.mark.asyncio
async def test_upsert_receipt_refuses_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(org_deletion, "NON_ERASABLE_STORES", frozenset({"billing"}))
    session = AsyncMock()
    receipt = org_deletion._ReceiptWrite(job_id="j", store="billing", status="verified")
    call = org_deletion._upsert_receipt(session, receipt)
    with pytest.raises(ValueError, match="non-erasable"):
        await call


@pytest.mark.asyncio
async def test_all_receipts_verified_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def verified(_s, _j, store):
        return store == "postgres"

    monkeypatch.setattr(org_deletion, "_receipt_verified", verified)
    assert await org_deletion._all_receipts_verified(AsyncMock(), "j") is False


@pytest.mark.asyncio
async def test_stage_clickhouse_empty_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_CLICKHOUSE_DSN", raising=False)
    settings = MagicMock(clickhouse_dsn=None)
    with pytest.raises(RuntimeError, match="CLICKHOUSE_DSN"):
        await org_deletion._stage_clickhouse(
            settings, org_id="00000000-0000-0000-0000-000000000001"
        )


@pytest.mark.asyncio
async def test_stage_objectstore_missing_endpoint_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    settings = MagicMock(s3_endpoint=None)
    with pytest.raises(RuntimeError, match="S3_ENDPOINT"):
        await org_deletion._stage_objectstore(settings, org_id="o", uris=[])


@pytest.mark.asyncio
async def test_optional_stores_skip_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_claimable_session_execute())
    _wire_run(monkeypatch, session)
    settings = MagicMock(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url=None,
        clickhouse_dsn=None,
        s3_endpoint=None,
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    monkeypatch.delenv("CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_CLICKHOUSE_DSN", raising=False)

    stage_ch = AsyncMock()
    stage_redis = AsyncMock()
    stage_s3 = AsyncMock()
    monkeypatch.setattr(org_deletion, "_resolve_archived_uris", AsyncMock(return_value=[]))
    monkeypatch.setattr(org_deletion, "_stage_postgres", AsyncMock())
    monkeypatch.setattr(org_deletion, "_stage_clickhouse", stage_ch)
    monkeypatch.setattr(org_deletion, "_stage_redis", stage_redis)
    monkeypatch.setattr(org_deletion, "_stage_objectstore", stage_s3)
    monkeypatch.setattr(org_deletion, "_publish_model_policy_invalidate", AsyncMock())
    monkeypatch.setattr(org_deletion, "_audit_append", AsyncMock())
    monkeypatch.setattr(org_deletion, "_receipt_digests", AsyncMock(return_value={}))
    monkeypatch.setattr(org_deletion, "_receipt_verified", AsyncMock(return_value=False))
    upsert = AsyncMock()
    monkeypatch.setattr(org_deletion, "_upsert_receipt", upsert)
    monkeypatch.setattr(org_deletion, "_all_receipts_verified", AsyncMock(return_value=True))

    out = await org_deletion._run_delete(job_id="j", org_id="o")
    assert out["status"] == "succeeded"
    stage_ch.assert_not_awaited()
    stage_redis.assert_not_awaited()
    stage_s3.assert_not_awaited()
    skipped = {
        c.args[1].store
        for c in upsert.await_args_list
        if getattr(c.args[1], "error", None) == "unconfigured"
    }
    assert skipped == {"clickhouse", "redis", "objectstore"}


@pytest.mark.asyncio
async def test_stage_redis_missing_url_raises() -> None:
    settings = MagicMock(redis_url=None)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        await org_deletion._stage_redis(settings, org_id="org-1")


@pytest.mark.asyncio
async def test_stage_objectstore_propagates_uri_delete_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ALLOW_INSECURE_HTTP", "1")
    settings = MagicMock(s3_endpoint="http://localhost:9000")

    def boom(_uri, *, settings=None):
        del settings
        raise RuntimeError("uri delete failed")

    monkeypatch.setattr("app.objectstore_client.delete_uri", boom)
    monkeypatch.setattr("app.objectstore_client.delete_org_prefix", MagicMock())
    with pytest.raises(RuntimeError, match="uri delete failed"):
        await org_deletion._stage_objectstore(
            settings, org_id="o", uris=["s3://ibex-sessions/o/a.json"]
        )


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


async def _run_delete_outcome(
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt_verified: bool,
    all_verified: bool,
) -> tuple[dict[str, str], AsyncMock | None]:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_claimable_session_execute())
    _wire_run(monkeypatch, session)
    stage_pg = _stub_store_pipeline(
        monkeypatch, receipt_verified=receipt_verified, all_verified=all_verified
    )
    out = await org_deletion._run_delete(job_id="j", org_id="o")
    return out, stage_pg


@pytest.mark.asyncio
async def test_incomplete_receipts_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    out, _ = await _run_delete_outcome(
        monkeypatch, receipt_verified=False, all_verified=False
    )
    assert out["status"] == "failed"


@pytest.mark.asyncio
async def test_skip_verified_store_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    out, stage_pg = await _run_delete_outcome(
        monkeypatch, receipt_verified=True, all_verified=True
    )
    assert out["status"] == "succeeded"
    assert stage_pg is not None
    stage_pg.assert_not_awaited()


@pytest.mark.asyncio
async def test_require_no_hold_raises() -> None:
    session = AsyncMock()
    hold = AsyncMock(return_value=True)
    with (
        patch.object(org_deletion, "_has_active_legal_hold", hold),
        pytest.raises(RuntimeError, match="legal_hold_active"),
    ):
        await org_deletion._require_no_hold(session, "o")
