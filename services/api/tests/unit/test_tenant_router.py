"""Unit tests for tenant ping router logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.routers import tenant as tenant_mod


@pytest.mark.asyncio
async def test_tenant_ping_found_and_missing() -> None:
    org = uuid4()
    token = ValidateResult(org_id=org, permissions=0)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=org))
    )
    result = await tenant_mod.tenant_ping(token, session)
    assert result["org_id"] == str(org)

    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    with pytest.raises(ApiError) as exc:
        await tenant_mod.tenant_ping(token, session)
    assert exc.value.code == "NOT_FOUND"
