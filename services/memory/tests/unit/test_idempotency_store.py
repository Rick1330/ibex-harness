"""Unit tests for idempotency Redis store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.idempotency.redis_store import (
    ClaimKind,
    IdempotencyRecord,
    IdempotencyState,
    IdempotencyToken,
    RedisIdempotencyStore,
    pending_record,
    redis_key,
)


def _mock_redis(*, cas_result: int = 1) -> AsyncMock:
    client = AsyncMock()
    client.register_script = MagicMock(return_value=AsyncMock(return_value=cas_result))
    return client


@pytest.fixture
def token() -> IdempotencyToken:
    return IdempotencyToken(org_id=uuid4(), key="idem-key")


@pytest.mark.asyncio
async def test_claim_miss_on_setnx(token: IdempotencyToken) -> None:
    client = _mock_redis()
    client.set = AsyncMock(return_value=True)
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.MISS
    assert outcome.record is not None
    assert outcome.record.state == IdempotencyState.PENDING


@pytest.mark.asyncio
async def test_claim_hit_on_completed(token: IdempotencyToken) -> None:
    completed = IdempotencyRecord(
        fingerprint="fp1",
        state=IdempotencyState.COMPLETED,
        status=201,
        body=b"{}",
    )
    client = _mock_redis()
    client.set = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=completed.to_json().encode())
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.HIT
    assert outcome.record is not None
    assert outcome.record.status == 201


@pytest.mark.asyncio
async def test_claim_conflict_on_fingerprint_mismatch(token: IdempotencyToken) -> None:
    pending = pending_record("other-fp")
    client = _mock_redis()
    client.set = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=pending.to_json().encode())
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.CONFLICT


@pytest.mark.asyncio
async def test_claim_in_progress(token: IdempotencyToken) -> None:
    pending = pending_record("fp1")
    client = _mock_redis()
    client.set = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=pending.to_json().encode())
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.IN_PROGRESS


@pytest.mark.asyncio
async def test_commit_and_release(token: IdempotencyToken) -> None:
    client = _mock_redis()
    cas = client.register_script.return_value
    store = RedisIdempotencyStore(client)
    await store.commit(token, fingerprint="fp1", status=201, body=b"{}")
    cas.assert_awaited()
    await store.release(token, "fp1")
    assert cas.await_count == 2


@pytest.mark.asyncio
async def test_commit_skips_stale_owner(token: IdempotencyToken) -> None:
    client = _mock_redis(cas_result=0)
    cas = client.register_script.return_value
    store = RedisIdempotencyStore(client)
    await store.commit(token, fingerprint="fp-old", status=200, body=b"old")
    cas.assert_awaited_once()


def test_redis_key_prefixes_org_id(token: IdempotencyToken) -> None:
    assert redis_key(token) == f"{token.org_id}:idempotency:{token.key}"


def test_record_roundtrip_json() -> None:
    rec = IdempotencyRecord(
        fingerprint="fp",
        state=IdempotencyState.COMPLETED,
        status=201,
        body=b'{"ok":true}',
    )
    parsed = IdempotencyRecord.from_json(rec.to_json())
    assert parsed.fingerprint == "fp"
    assert parsed.status == 201


def test_record_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        IdempotencyRecord.from_json('{"v":99,"state":"pending","fp":"x"}')


@pytest.mark.asyncio
async def test_claim_race_retry_miss(token: IdempotencyToken) -> None:
    client = _mock_redis()
    client.set = AsyncMock(side_effect=[False, True])
    client.get = AsyncMock(return_value=None)
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.MISS


@pytest.mark.asyncio
async def test_claim_returns_in_progress_when_still_missing(token: IdempotencyToken) -> None:
    client = _mock_redis()
    client.set = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=None)
    store = RedisIdempotencyStore(client)
    outcome = await store.claim(token, "fp1")
    assert outcome.kind == ClaimKind.IN_PROGRESS


@pytest.mark.asyncio
async def test_release_uses_cas(token: IdempotencyToken) -> None:
    client = _mock_redis(cas_result=0)
    cas = client.register_script.return_value
    store = RedisIdempotencyStore(client)
    await store.release(token, "fp1")
    cas.assert_awaited_once()
