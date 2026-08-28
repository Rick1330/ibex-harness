"""Unit tests for FastAPI deps and auth helpers."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.client import StaticTokenValidator, ValidateResult, parse_authorization_header
from app.auth.errors import AuthFailedError
from app.deps import (
    get_idempotency_store,
    get_redis,
    get_session_factory,
    get_validator,
    get_write_orchestrator,
    require_memory_write,
    require_token,
)
from app.main import MemoryAppState
from app.permissions import MEMORY_READ, MEMORY_WRITE


def test_parse_authorization_header_valid() -> None:
    assert parse_authorization_header("Bearer abc") == "abc"


def test_parse_authorization_header_missing() -> None:
    with pytest.raises(AuthFailedError):
        parse_authorization_header(None)


def test_get_validator_missing_returns_503() -> None:
    request = MagicMock()
    request.app.state.memory = MemoryAppState()
    with pytest.raises(HTTPException) as exc:
        get_validator(request)
    assert exc.value.status_code == 503


def test_get_write_orchestrator_missing_returns_503() -> None:
    request = MagicMock()
    request.app.state.memory = MemoryAppState()
    with pytest.raises(HTTPException) as exc:
        get_write_orchestrator(request)
    assert exc.value.status_code == 503


def test_get_session_factory_missing_returns_503() -> None:
    request = MagicMock()
    request.app.state.memory = MemoryAppState()
    with pytest.raises(HTTPException) as exc:
        get_session_factory(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_require_token_success() -> None:
    org_id = uuid4()
    validator = StaticTokenValidator(
        {"tok": ValidateResult(org_id=org_id, permissions=MEMORY_WRITE)}
    )
    got = await require_token("Bearer tok", validator)
    assert got.org_id == org_id


@pytest.mark.asyncio
async def test_require_token_auth_failed() -> None:
    validator = StaticTokenValidator({})
    with pytest.raises(HTTPException) as exc:
        await require_token("Bearer bad", validator)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_memory_write_forbidden() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=MEMORY_READ)
    with pytest.raises(HTTPException) as exc:
        require_memory_write(token)
    assert exc.value.status_code == 403


def test_get_idempotency_and_redis_from_state() -> None:
    state = MemoryAppState()
    sentinel_store = object()
    sentinel_redis = object()
    state.idempotency_store = sentinel_store  # type: ignore[assignment]
    state.redis = sentinel_redis  # type: ignore[assignment]
    request = MagicMock()
    request.app.state.memory = state
    assert get_idempotency_store(request) is sentinel_store
    assert get_redis(request) is sentinel_redis


@pytest.mark.asyncio
async def test_static_validator_unavailable() -> None:
    validator = StaticTokenValidator({}, available=False)
    with pytest.raises(HTTPException):
        await require_token("Bearer x", validator)


@pytest.mark.asyncio
async def test_require_token_auth_unavailable() -> None:
    validator = StaticTokenValidator({}, available=False)
    with pytest.raises(HTTPException) as exc:
        await require_token("Bearer tok", validator)
    assert exc.value.status_code == 503
