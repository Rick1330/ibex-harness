"""Outbox watermark probe: "no rows yet" and "the probe failed" are different states.

A null ``outbox_max_aggregate_seq`` used to mean either, so a failing query made
the operator health page look healthy. These tests pin the distinction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import platform as platform_mod
from app.routers.platform import platform_health
from tests.unit.platform_health_test_support import authed_request, claims


def _session_returning(value: object) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: value))
    return session


def _factory_for(session: AsyncMock) -> MagicMock:
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


async def _health_with_session(session: AsyncMock) -> object:
    """Run the route with a working session factory over ``session``."""
    req = authed_request()
    req.app.state.api.session_factory = _factory_for(session)
    session_claims = claims()
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=session_claims),
        patch.object(platform_mod, "_postgres_status", AsyncMock(return_value="ok")),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
        patch.object(platform_mod, "session_with_org", return_value=_factory_for(session)()),
    ):
        return await platform_health(req, session_claims)


@pytest.mark.asyncio
async def test_outbox_probe_without_session_is_unavailable() -> None:
    assert await platform_mod._probe_outbox(None, uuid4()) == (None, "unavailable")


@pytest.mark.asyncio
async def test_outbox_probe_query_error_is_degraded() -> None:
    """A failed query is not an empty outbox: it must not be swallowed into None."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("boom"))
    with patch.object(platform_mod, "session_with_org", return_value=_factory_for(session)()):
        assert await platform_mod._probe_outbox(MagicMock(), uuid4()) == (None, "degraded")


@pytest.mark.asyncio
async def test_outbox_probe_bad_scalar_is_degraded() -> None:
    session = _session_returning("not-int")
    with patch.object(platform_mod, "session_with_org", return_value=_factory_for(session)()):
        assert await platform_mod._probe_outbox(MagicMock(), uuid4()) == (None, "degraded")


@pytest.mark.asyncio
async def test_outbox_probe_open_failure_is_degraded() -> None:
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch.object(platform_mod, "session_with_org", return_value=cm):
        assert await platform_mod._probe_outbox(MagicMock(), uuid4()) == (None, "degraded")


@pytest.mark.asyncio
async def test_outbox_probe_empty_table_is_ok() -> None:
    session = _session_returning(0)
    with patch.object(platform_mod, "session_with_org", return_value=_factory_for(session)()):
        assert await platform_mod._probe_outbox(MagicMock(), uuid4()) == (0, "ok")


@pytest.mark.asyncio
async def test_platform_health_outbox_empty_table_is_healthy() -> None:
    """An empty outbox answers 0 and stays healthy; it is not a probe failure."""
    out = await _health_with_session(_session_returning(0))
    assert out.outbox_max_aggregate_seq == 0
    assert out.dependency_health["outbox"] == "ok"
    assert out.degraded_mode is False


@pytest.mark.asyncio
async def test_platform_health_outbox_query_failure_is_degraded() -> None:
    """A DB failure inside the watermark query must not render as a healthy page."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("outbox table unavailable"))
    out = await _health_with_session(session)
    assert out.outbox_max_aggregate_seq is None
    assert out.dependency_health["outbox"] == "degraded"
    assert out.degraded_mode is True


@pytest.mark.asyncio
async def test_platform_health_outbox_factory_raises() -> None:
    req = authed_request()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("db"))
    cm.__aexit__ = AsyncMock(return_value=None)
    req.app.state.api.session_factory = MagicMock()
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=claims()),
        patch.object(platform_mod, "_postgres_status", AsyncMock(return_value="unavailable")),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
        patch.object(platform_mod, "session_with_org", return_value=cm),
    ):
        out = await platform_health(req, claims())
    assert out.outbox_max_aggregate_seq is None
    assert out.dependency_health["postgres"] == "unavailable"
    assert out.dependency_health["outbox"] == "degraded"
    assert out.degraded_mode is True
