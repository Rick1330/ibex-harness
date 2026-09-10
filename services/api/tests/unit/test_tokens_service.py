"""Unit tests for token service error mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from apierror_py import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INVALID_TOKEN,
    NOT_FOUND,
    PERMISSION_ELEVATION_DENIED,
)
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    TokenNotFoundError,
)
from authclient.permissions import ADMIN, MEMORY_READ
from authclient.tokens import FakeTokenManager, ListTokensWire, TokenMetadataWire

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.pagination import ListQuery
from app.schemas.tokens import TokenCreateRequest
from app.services import tokens as token_service
from app.services.tokens import TokenAccess, create_token, get_token, list_tokens, revoke_token


def _access(mgr, *, permissions: int = ADMIN) -> TokenAccess:
    org = uuid4()
    return TokenAccess(
        token=ValidateResult(org_id=org, permissions=permissions, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (InsufficientPermissionsError(), INSUFFICIENT_PERMISSIONS),
        (AuthFailedError("x"), INVALID_TOKEN),
        (AuthUnavailableError(), AUTH_UNAVAILABLE),
    ],
)
async def test_create_maps_auth_errors(exc: BaseException, code: str) -> None:
    session = AsyncMock()
    mgr = FakeTokenManager()
    mgr.create_error = exc
    access = _access(mgr)
    body = TokenCreateRequest(name="t", permissions=["memory:read"])
    with pytest.raises(ApiError) as raised:
        await create_token(session, access, body)
    assert raised.value.code == code


@pytest.mark.asyncio
async def test_list_maps_not_found() -> None:
    mgr = FakeTokenManager()
    mgr.list_error = TokenNotFoundError()
    access = _access(mgr)
    query = ListQuery()
    with pytest.raises(ApiError) as raised:
        await list_tokens(access, query)
    assert raised.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_revoke_maps_not_found() -> None:
    mgr = FakeTokenManager()
    mgr.revoke_error = TokenNotFoundError()
    access = _access(mgr)
    tid = uuid4()
    with pytest.raises(ApiError) as raised:
        await revoke_token(access, tid)
    assert raised.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_map_token_rpc_unknown_is_auth_unavailable() -> None:
    err = token_service._map_token_rpc(RuntimeError("boom"))
    assert err.code == AUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_create_elevation_denied() -> None:
    session = AsyncMock()
    access = _access(FakeTokenManager(), permissions=MEMORY_READ)
    body = TokenCreateRequest(name="t", permissions=["admin:user_manage"])
    with pytest.raises(ApiError) as raised:
        await create_token(session, access, body)
    assert raised.value.code == PERMISSION_ELEVATION_DENIED


@pytest.mark.asyncio
async def test_get_token_paginates_until_match() -> None:
    org = uuid4()
    tid = uuid4()
    mgr = FakeTokenManager()

    async def _list(*, org_id: str, access_token: str, cursor: str = "", limit: int = 50):
        del org_id, access_token, limit
        if cursor == "":
            return ListTokensWire(
                tokens=[
                    TokenMetadataWire(
                        token_id=str(uuid4()),
                        name="other",
                        prefix="p",
                        permissions=MEMORY_READ,
                        created_at=datetime.now(UTC),
                    )
                ],
                next_cursor="page2",
            )
        return ListTokensWire(
            tokens=[
                TokenMetadataWire(
                    token_id=str(tid),
                    name="hit",
                    prefix="p",
                    permissions=MEMORY_READ,
                    created_at=datetime.now(UTC),
                )
            ],
            next_cursor="",
        )

    mgr.list = _list  # type: ignore[method-assign]
    access = TokenAccess(
        token=ValidateResult(org_id=org, permissions=ADMIN, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )
    row = await get_token(access, tid)
    assert row.id == tid
    assert row.name == "hit"


@pytest.mark.asyncio
async def test_get_token_complete_miss_is_not_found() -> None:
    org = uuid4()
    mgr = FakeTokenManager()
    mgr.seed(
        str(org),
        TokenMetadataWire(
            token_id=str(uuid4()),
            name="other",
            prefix="p",
            permissions=MEMORY_READ,
            created_at=datetime.now(UTC),
        ),
    )
    access = TokenAccess(
        token=ValidateResult(org_id=org, permissions=ADMIN, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )
    with pytest.raises(ApiError) as raised:
        await get_token(access, uuid4())
    assert raised.value.code == NOT_FOUND


@pytest.mark.asyncio
async def test_get_token_cursor_cycle_is_auth_unavailable() -> None:
    org = uuid4()
    mgr = FakeTokenManager()

    async def _list(*, org_id: str, access_token: str, cursor: str = "", limit: int = 50):
        del org_id, access_token, limit
        return ListTokensWire(
            tokens=[
                TokenMetadataWire(
                    token_id=str(uuid4()),
                    name="loop",
                    prefix="p",
                    permissions=MEMORY_READ,
                    created_at=datetime.now(UTC),
                )
            ],
            next_cursor=cursor or "same",
        )

    mgr.list = _list  # type: ignore[method-assign]
    access = TokenAccess(
        token=ValidateResult(org_id=org, permissions=ADMIN, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )
    with pytest.raises(ApiError) as raised:
        await get_token(access, uuid4())
    assert raised.value.code == AUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_get_token_deadline_exhausted_is_auth_unavailable() -> None:
    org = uuid4()
    mgr = FakeTokenManager()
    calls = {"n": 0}

    async def _list(*, org_id: str, access_token: str, cursor: str = "", limit: int = 50):
        del org_id, access_token, limit
        calls["n"] += 1
        return ListTokensWire(
            tokens=[],
            next_cursor=f"c{calls['n']}",
        )

    mgr.list = _list  # type: ignore[method-assign]
    access = TokenAccess(
        token=ValidateResult(org_id=org, permissions=ADMIN, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )
    with (
        patch("app.services.tokens._GET_BY_ID_DEADLINE_S", 0.0),
        pytest.raises(ApiError) as raised,
    ):
        await get_token(access, uuid4())
    assert raised.value.code == AUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_valid_cidr_accepted_but_not_persisted() -> None:
    session = AsyncMock()
    mgr = FakeTokenManager()
    access = _access(mgr)
    body = TokenCreateRequest(
        name="cidr",
        permissions=["memory:read"],
        allowed_ips=["10.0.0.0/8"],
    )
    created = await create_token(session, access, body)
    assert created.token.startswith("ibex_pat_")
    assert "allowed_ips" not in created.model_dump()


@pytest.mark.asyncio
async def test_allowed_ips_none_validator_passthrough() -> None:
    body = TokenCreateRequest(name="n", permissions=["memory:read"], allowed_ips=None)
    assert body.allowed_ips is None
