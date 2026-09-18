"""Cross-store org-deletion absence proof (Postgres + ClickHouse + Redis + MinIO).

Requires opt-in env (set by worker-integration CI):
  POSTGRES_TEST_DSN, REDIS_URL, CLICKHOUSE_DSN, S3_ENDPOINT (+ S3 creds/bucket/key),
  IBEX_ORG_DELETION_DEPLOYED_STORES=postgres,clickhouse,redis,objectstore
"""

from __future__ import annotations

import base64
import os
import secrets
import uuid
from collections.abc import AsyncIterator

import pytest
import redis as redis_sync
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.tasks import org_deletion

pytestmark = pytest.mark.integration

_OPT_IN = "IBEX_ORG_DELETION_MULTISTORE_TEST"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _multistore_opted_in() -> bool:
    for key in ("CI", _OPT_IN, "IBEX_WORKER_INTEGRATION_TESTS"):
        if _truthy(key):
            return True
    return False


def _env_first(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return ""


def _collect_multistore_env() -> dict[str, str]:
    return {
        "postgres": _env_first("POSTGRES_TEST_DSN", "DATABASE_URL"),
        "redis": _env_first("REDIS_URL"),
        "clickhouse": _env_first("CLICKHOUSE_DSN", "IBEX_WORKER_CLICKHOUSE_DSN"),
        "s3": _env_first("S3_ENDPOINT"),
    }


def _skip_incomplete(env: dict[str, str]) -> None:
    missing = [name for name, value in env.items() if not value]
    if missing:
        pytest.skip(f"multi-store deletion test missing env for: {', '.join(missing)}")


@pytest.fixture(scope="module")
def multistore_env() -> dict[str, str]:
    if not _multistore_opted_in():
        pytest.skip(f"set {_OPT_IN}=1 (or CI) to run multi-store deletion absence tests")
    env = _collect_multistore_env()
    _skip_incomplete(env)
    return env


def _async_pg_dsn(dsn: str) -> str:
    """Normalize CI/local DSNs for SQLAlchemy async (asyncpg)."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn.removeprefix("postgres://")
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn.removeprefix("postgresql://")
    return dsn


@pytest.fixture
async def async_pg(multistore_env: dict[str, str]) -> AsyncIterator[AsyncSession]:
    eng = create_async_engine(_async_pg_dsn(multistore_env["postgres"]))
    SessionLocal = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await eng.dispose()


def _master_key_b64() -> str:
    existing = os.environ.get("S3_MASTER_KEY_B64") or os.environ.get("OBJECTSTORE_MASTER_KEY_B64")
    if existing:
        return existing
    return base64.b64encode(secrets.token_bytes(32)).decode()


async def _seed_org(session: AsyncSession) -> tuple[str, str]:
    org_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    slug = f"del-{org_id[:8]}"
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.organizations (id, name, slug, status)
            VALUES (CAST(:id AS uuid), :name, :slug, 'active')
            """
        ),
        {"id": org_id, "name": f"Delete Me {slug}", "slug": slug},
    )
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)
            VALUES (CAST(:job AS uuid), CAST(:org AS uuid), 'pending')
            """
        ),
        {"job": job_id, "org": org_id},
    )
    await session.commit()
    return org_id, job_id


def _seed_redis(org_id: str, redis_url: str) -> str:
    key = f"{org_id}:memory:fixture-{uuid.uuid4().hex[:8]}"
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        client.set(key, "residual-should-be-deleted")
    finally:
        client.close()
    return key


def _seed_clickhouse(org_id: str, dsn: str) -> None:
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    http = shared_clickhouse_client()
    url, auth = _http_endpoint(dsn)
    agent = str(uuid.uuid4())
    q = f"""
    INSERT INTO ibex.llm_traces (
      request_id, org_id, agent_id, model, provider, is_streaming,
      input_tokens, output_tokens, total_tokens,
      auth_latency_ms, directive_latency_ms, provider_ttfb_ms, total_latency_ms,
      status_code, is_complete, error_code, requested_at, completed_at
    ) VALUES (
      'req-del-test', '{org_id}', '{agent}', 'fixture', 'test', 0,
      1, 1, 2,
      1, 1, 1, 1,
      200, 1, '', now64(3), now64(3)
    )
    """
    resp = http.post(url, params={"query": q}, auth=auth, timeout=30)
    if resp.status_code >= 300:
        pytest.fail(f"clickhouse seed failed: {resp.status_code} {resp.text[:300]}")


def _ch_count(org_id: str, dsn: str) -> int:
    from app.extraction.clickhouse_traces import _http_endpoint, shared_clickhouse_client

    http = shared_clickhouse_client()
    url, auth = _http_endpoint(dsn)
    q = f"SELECT count() FROM ibex.llm_traces WHERE org_id = '{org_id}'"
    resp = http.post(url, params={"query": q}, auth=auth, timeout=30)
    if resp.status_code >= 300:
        pytest.fail(f"clickhouse count failed: {resp.status_code} {resp.text[:200]}")
    return int(resp.text.strip() or "0")


def _seed_objectstore(org_id: str, settings: Settings) -> str:
    from app.objectstore_client import put_encrypted_json

    key = f"{org_id}/capture/full/fixture.json"
    return put_encrypted_json(key, b'{"prompt":"seed"}', settings=settings)


def _object_exists(org_id: str, settings: Settings) -> bool:
    from app.objectstore_client import _list_keys, _load_cfg

    cfg = _load_cfg(settings)
    keys = _list_keys(cfg, f"{org_id}/")
    return len(keys) > 0


def _redis_key_exists(redis_url: str, key: str) -> bool:
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        return bool(client.exists(key))
    finally:
        client.close()


async def _org_deleted(session: AsyncSession, org_id: str) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT status, deleted_at IS NOT NULL
                FROM ibex_core.organizations
                WHERE id = CAST(:o AS uuid)
                """
            ),
            {"o": org_id},
        )
    ).first()
    return row is not None and row[0] == "cancelled" and bool(row[1])


@pytest.mark.asyncio
async def test_org_deletion_clears_all_four_stores(
    monkeypatch: pytest.MonkeyPatch,
    multistore_env: dict[str, str],
    async_pg: AsyncSession,
) -> None:
    monkeypatch.setenv("S3_ALLOW_INSECURE_HTTP", "1")
    monkeypatch.setenv(
        "IBEX_ORG_DELETION_DEPLOYED_STORES", "postgres,clickhouse,redis,objectstore"
    )
    master = _master_key_b64()
    monkeypatch.setenv("S3_MASTER_KEY_B64", master)
    monkeypatch.setenv("S3_ACCESS_KEY", os.environ.get("S3_ACCESS_KEY", "minioadmin"))
    monkeypatch.setenv("S3_SECRET_KEY", os.environ.get("S3_SECRET_KEY", "minioadmin"))
    monkeypatch.setenv(
        "S3_BUCKET_SESSIONS", os.environ.get("S3_BUCKET_SESSIONS", "ibex-sessions")
    )
    monkeypatch.setenv("S3_REGION", os.environ.get("S3_REGION", "us-east-1"))

    settings = Settings(
        database_url=_async_pg_dsn(multistore_env["postgres"]),
        redis_url=multistore_env["redis"],
        clickhouse_dsn=multistore_env["clickhouse"],
        s3_endpoint=multistore_env["s3"],
        s3_access_key=os.environ["S3_ACCESS_KEY"],
        s3_secret_key=os.environ["S3_SECRET_KEY"],
        s3_bucket_sessions=os.environ["S3_BUCKET_SESSIONS"],
        s3_region=os.environ.get("S3_REGION", "us-east-1"),
        s3_master_key_b64=master,
        org_deletion_deployed_stores="postgres,clickhouse,redis,objectstore",
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)

    org_id, job_id = await _seed_org(async_pg)
    rkey = _seed_redis(org_id, multistore_env["redis"])
    assert _redis_key_exists(multistore_env["redis"], rkey)
    _seed_clickhouse(org_id, multistore_env["clickhouse"])
    assert _ch_count(org_id, multistore_env["clickhouse"]) >= 1
    _seed_objectstore(org_id, settings)
    assert _object_exists(org_id, settings)

    out = await org_deletion._run_delete(job_id=job_id, org_id=org_id)
    assert out["status"] == "succeeded", out

    async_pg.expire_all()
    assert await _org_deleted(async_pg, org_id)
    assert not _redis_key_exists(multistore_env["redis"], rkey)
    assert _ch_count(org_id, multistore_env["clickhouse"]) == 0
    assert not _object_exists(org_id, settings)

    rows = (
        await async_pg.execute(
            text(
                """
                SELECT store, status, error FROM ibex_core.deletion_store_receipts
                WHERE job_id = CAST(:j AS uuid) ORDER BY store
                """
            ),
            {"j": job_id},
        )
    ).fetchall()
    by_store = {r[0]: (r[1], r[2]) for r in rows}
    for store in org_deletion._STORES:
        assert by_store[store][0] == "verified", by_store
        assert by_store[store][1] is None


@pytest.mark.asyncio
async def test_deployed_misconfigured_store_fails_not_verified(
    monkeypatch: pytest.MonkeyPatch,
    multistore_env: dict[str, str],
    async_pg: AsyncSession,
) -> None:
    """Deliberate misconfig of a deployed store must fail the job (B1)."""
    settings = Settings(
        database_url=_async_pg_dsn(multistore_env["postgres"]),
        redis_url=multistore_env["redis"],
        clickhouse_dsn=None,  # misconfigured
        s3_endpoint=None,
        org_deletion_deployed_stores="postgres,clickhouse,redis,objectstore",
    )
    monkeypatch.setattr(org_deletion, "get_settings", lambda: settings)
    monkeypatch.delenv("CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("S3_ENDPOINT", raising=False)

    org_id, job_id = await _seed_org(async_pg)
    with pytest.raises(RuntimeError, match="deployed but unreachable"):
        await org_deletion._run_delete(job_id=job_id, org_id=org_id)

    row = (
        await async_pg.execute(
            text(
                """
                SELECT status, error FROM ibex_core.deletion_store_receipts
                WHERE job_id = CAST(:j AS uuid) AND store = 'clickhouse'
                """
            ),
            {"j": job_id},
        )
    ).first()
    assert row is not None
    assert row[0] == "failed"
    assert row[1] == "store_unreachable"
    job = (
        await async_pg.execute(
            text(
                "SELECT status FROM ibex_core.org_deletion_jobs WHERE id = CAST(:j AS uuid)"
            ),
            {"j": job_id},
        )
    ).first()
    assert job is not None
    assert job[0] == "failed"
