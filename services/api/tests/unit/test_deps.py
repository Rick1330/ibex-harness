"""Unit tests for FastAPI dependency helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import (
    get_session_factory,
    get_validator,
    operator_org_session,
    org_id_from_token,
    org_session,
    require_token,
)
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization


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

    with pytest.raises(ApiError) as exc:
        await require_token(authorization=None, validator=validator)
    assert exc.value.code == "MISSING_TOKEN"

    with pytest.raises(ApiError) as exc:
        await require_token(authorization="Bearer unknown", validator=validator)
    assert exc.value.code == "INVALID_TOKEN"

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


@pytest.mark.asyncio
async def test_operator_org_session_binds_verified_org_and_closes() -> None:
    operator = OperatorSessionAuthorization(
        org_id=uuid4(), permissions=1, session_id="sid", subject="user-1"
    )
    session = MagicMock()
    factory = MagicMock()
    with patch("app.deps.session_with_org") as sw:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        sw.return_value = ctx
        agen = operator_org_session(operator, factory)
        yielded = await agen.__anext__()
        assert yielded is session
        await agen.aclose()
    sw.assert_called_once_with(factory, str(operator.org_id))
    ctx.__aexit__.assert_awaited_once()
