"""Unit tests for memory write HTTP support helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.exceptions import DuplicateMemoryError, ValidationError
from app.idempotency.redis_store import ClaimKind, ClaimOutcome, IdempotencyRecord, IdempotencyState
from app.routers.memory_write_support import (
    begin_idempotency,
    commit_idempotency,
    http_error_for_write,
    release_idempotency,
)


@pytest.mark.asyncio
async def test_begin_idempotency_skips_without_key() -> None:
    handle = await begin_idempotency(
        store=AsyncMock(),
        org_id=uuid4(),
        idempotency_key=None,
        fingerprint="fp",
    )
    assert handle.token is None


@pytest.mark.asyncio
async def test_begin_idempotency_hit_returns_json() -> None:
    store = AsyncMock()
    record = IdempotencyRecord(
        fingerprint="fp",
        state=IdempotencyState.COMPLETED,
        status=201,
        body=b'{"ok":true}',
    )
    store.claim = AsyncMock(return_value=ClaimOutcome(kind=ClaimKind.HIT, record=record))
    result = await begin_idempotency(
        store=store,
        org_id=uuid4(),
        idempotency_key="k",
        fingerprint="fp",
    )
    assert isinstance(result, JSONResponse)
    assert result.status_code == 201


@pytest.mark.asyncio
async def test_release_and_commit_when_active() -> None:
    store = AsyncMock()
    org_id = uuid4()
    from app.idempotency.redis_store import IdempotencyToken
    from app.routers.memory_write_support import IdempotencyHandle

    handle = IdempotencyHandle(
        store=store,
        token=IdempotencyToken(org_id=org_id, key="k"),
        fingerprint="fp",
    )
    await release_idempotency(handle)
    store.release.assert_awaited_once()
    await commit_idempotency(handle, status=201, body=b"{}")
    store.commit.assert_awaited_once()


def test_http_error_for_write_maps_duplicate() -> None:
    exc = http_error_for_write(DuplicateMemoryError(uuid4()))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 409


def test_http_error_for_write_maps_validation() -> None:
    exc = http_error_for_write(ValidationError("bad", field="content"))
    assert exc.status_code == 400


@pytest.mark.asyncio
async def test_parse_idempotency_key_rejects_too_long() -> None:
    from app.routers.memory_write_support import parse_idempotency_key

    with pytest.raises(HTTPException) as exc:
        parse_idempotency_key("k" * 300)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_begin_idempotency_treats_whitespace_as_absent() -> None:
    handle = await begin_idempotency(
        store=AsyncMock(),
        org_id=uuid4(),
        idempotency_key="   ",
        fingerprint="fp",
    )
    assert handle.token is None
