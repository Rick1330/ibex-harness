"""Unit tests for token service error mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from apierror_py import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INVALID_TOKEN,
    NOT_FOUND,
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
from app.services.tokens import TokenAccess, create_token, get_token, list_tokens, revoke_token


def _access(mgr, *, permissions: int = ADMIN) -> TokenAccess:
    org = uuid4()
    return TokenAccess(
        token=ValidateResult(org_id=org, permissions=permissions, user_id=str(uuid4())),
        access_token="secret",
        manager=mgr,
    )


@pytest.mark.asyncio
async def test_create_maps_auth_errors() -> None:
    session = AsyncMock()
    for exc, code in (
        (InsufficientPermissionsError(), INSUFFICIENT_PERMISSIONS),
        (AuthFailedError("x"), INVALID_TOKEN),
        (AuthUnavailableError(), AUTH_UNAVAILABLE),
    ):
        mgr = FakeTokenManager()
        mgr.create_error = exc
        access = _access(mgr)
        with pytest.raises(ApiError) as raised:
            await create_token(
                session,
                access,
                TokenCreateRequest(name="t", permissions=["memory:read"]),
            )
        assert raised.value.code == code


@pytest.mark.asyncio
async def test_list_and_revoke_map_not_found() -> None:
    mgr = FakeTokenManager()
    mgr.list_error = TokenNotFoundError()
    access = _access(mgr)
    with pytest.raises(ApiError) as raised:
        await list_tokens(access, ListQuery())
    assert raised.value.code == NOT_FOUND

    mgr2 = FakeTokenManager()
    mgr2.revoke_error = TokenNotFoundError()
    with pytest.raises(ApiError) as raised2:
        await revoke_token(_access(mgr2), uuid4())
    assert raised2.value.code == NOT_FOUND


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
    assert not hasattr(created, "allowed_ips") or "allowed_ips" not in created.model_dump()
