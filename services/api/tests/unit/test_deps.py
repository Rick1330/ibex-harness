"""Unit tests for FastAPI dependency helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import (
    get_session_factory,
    get_validator,
    org_id_from_token,
    org_session,
    require_token,
)
from app.errors import ApiError


@pytest.mark.asyncio
async def test_deps_require_token_and_org_session() -> None:
    org = uuid4()
    token = ValidateResult(org_id=org, permissions=0)
    assert org_id_from_token(token) == org

    request = MagicMock()
    request.app.state.api.validator = StaticTokenValidator({"t": token})
    request.app.state.api.session_factory = MagicMock()
    assert get_validator(request) is not None

    request.app.state.api.validator = None
    with pytest.raises(ApiError):
        get_validator(request)

    request.app.state.api.session_factory = None
    with pytest.raises(ApiError):
        get_session_factory(request)

    validator = StaticTokenValidator({"t": token})
    result = await require_token(authorization="Bearer t", validator=validator)
    assert result.org_id == org

    down = StaticTokenValidator({}, available=False)
    with pytest.raises(ApiError) as exc:
        await require_token(authorization="Bearer t", validator=down)
    assert exc.value.code == "AUTH_UNAVAILABLE"

    session = MagicMock()
    factory = MagicMock()
    with patch("app.deps.session_with_org") as sw:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        sw.return_value = ctx
        agen = org_session(token, factory)
        yielded = await agen.__anext__()
        assert yielded is session
        await agen.aclose()
