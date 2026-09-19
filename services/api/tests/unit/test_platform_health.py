"""Unit tests for operator platform health (4.P.5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apierror_py import INSUFFICIENT_PERMISSIONS, INVALID_TOKEN
from authclient.permissions import OPERATOR_METADATA_READ

from app.errors import ApiError
from app.routers import platform as platform_mod
from app.routers.platform import (
    _load_drill,
    _parse_backup_stamp,
    _parse_dlq_depth,
    _require_operator_session,
    platform_health,
)
from app.session_stub import SESSION_KIND_ACCESS, SessionClaims


def _claims(*, permissions: int = OPERATOR_METADATA_READ) -> SessionClaims:
    return SessionClaims(
        sub="user-1",
        org_id=uuid4(),
        permissions=permissions,
        session_kind=SESSION_KIND_ACCESS,
        exp=9999999999,
        iat=1,
        jti="jti-1",
        verify_method="HS256",
    )


def _authed_request(
    *,
    feature: bool = True,
    redis_url: str | None = "redis://localhost:6379/0",
) -> MagicMock:
    req = MagicMock()
    req.app.state.settings = MagicMock(
        operator_feature_enabled=feature,
        jwt_hmac_secret="sekrit",
        jwt_public_keys_pem=None,
        jwt_issuer="ibex",
        jwt_audience="ibex-dashboard",
        dashboard_session_cookie_name="ibex_session",
        redis_url=redis_url,
        platform_retention_horizon_days=90,
    )
    req.cookies = {"ibex_session": "valid.token.here"}
    api = MagicMock()
    api.ready = True
    validator = MagicMock()
    validator.ready = AsyncMock(return_value=True)
    api.validator = validator
    api.session_factory = None
    api.drain = MagicMock(is_draining=lambda: False)
    req.app.state.api = api
    return req


def test_parse_backup_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = tmp_path / "last-backup.txt"
    stamp.write_text("[backup] ok 2026-09-19T07:00:00+00:00\n", encoding="utf-8")
    monkeypatch.setattr(platform_mod, "_BACKUP_STAMP", stamp)
    assert _parse_backup_stamp() == datetime(2026, 9, 19, 7, 0, tzinfo=UTC)


def test_parse_backup_stamp_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_mod, "_BACKUP_STAMP", tmp_path / "missing.txt")
    assert _parse_backup_stamp() is None


def test_parse_backup_stamp_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = tmp_path / "gone.txt"
    stamp.write_text("x", encoding="utf-8")
    monkeypatch.setattr(platform_mod, "_BACKUP_STAMP", stamp)

    def boom(*_a: object, **_k: object) -> str:
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", boom)
    assert _parse_backup_stamp() is None


def test_parse_backup_stamp_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stamp = tmp_path / "bad.txt"
    stamp.write_text("not-a-timestamp\n", encoding="utf-8")
    monkeypatch.setattr(platform_mod, "_BACKUP_STAMP", stamp)
    assert _parse_backup_stamp() is None


def test_load_drill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "restore-drill-report.json"
    report.write_text(json.dumps({"milestone": "4.P.5"}), encoding="utf-8")
    monkeypatch.setattr(platform_mod, "_DRILL_REPORT", report)
    assert _load_drill()["milestone"] == "4.P.5"


def test_load_drill_bad_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "bad.json"
    report.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(platform_mod, "_DRILL_REPORT", report)
    assert _load_drill() is None


def test_parse_dlq_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_DLQ_DEPTH", raising=False)
    assert _parse_dlq_depth() is None
    monkeypatch.setenv("IBEX_DLQ_DEPTH", "7")
    assert _parse_dlq_depth() == 7
    monkeypatch.setenv("IBEX_DLQ_DEPTH", "nope")
    assert _parse_dlq_depth() is None


@pytest.mark.asyncio
async def test_platform_health_disabled() -> None:
    req = _authed_request(feature=False)
    with pytest.raises(ApiError) as exc:
        await platform_health(req)
    assert "operator feature disabled" in str(exc.value)


@pytest.mark.asyncio
async def test_platform_health_missing_cookie() -> None:
    req = _authed_request()
    req.cookies = {}
    with pytest.raises(ApiError) as exc:
        await platform_health(req)
    assert exc.value.code == INVALID_TOKEN


@pytest.mark.asyncio
async def test_platform_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_DLQ_DEPTH", "3")
    monkeypatch.setenv("IBEX_DEPLOY_IMAGE_DIGEST", "sha256:abc")
    req = _authed_request()
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=_claims()),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
    ):
        out = await platform_health(req)
    assert out.dlq_depth == 3
    assert out.deploy_image_digest == "sha256:abc"
    assert out.dependency_health["api"] == "ok"
    assert out.dependency_health["postgres"] == "unavailable"
    assert out.dependency_health["auth"] == "ok"
    assert out.degraded_mode is True


@pytest.mark.asyncio
async def test_platform_health_draining() -> None:
    req = _authed_request()
    req.app.state.api.drain = MagicMock(is_draining=lambda: True)
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=_claims()),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
    ):
        out = await platform_health(req)
    assert out.degraded_mode is True


@pytest.mark.asyncio
async def test_platform_health_postgres_ok() -> None:
    req = _authed_request()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[None, MagicMock(scalar_one=lambda: 42)],
    )
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    req.app.state.api.session_factory = MagicMock(return_value=cm)
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=_claims()),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
    ):
        out = await platform_health(req)
    assert out.dependency_health["postgres"] == "ok"
    assert out.outbox_max_aggregate_seq == 42
    assert out.degraded_mode is False


@pytest.mark.asyncio
async def test_platform_health_postgres_error() -> None:
    req = _authed_request()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
    cm.__aexit__ = AsyncMock(return_value=None)
    req.app.state.api.session_factory = MagicMock(return_value=cm)
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=_claims()),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
    ):
        out = await platform_health(req)
    assert out.dependency_health["postgres"] == "unavailable"
    assert out.degraded_mode is True


def test_require_session_no_secret() -> None:
    req = MagicMock()
    req.app.state.settings = MagicMock(
        operator_feature_enabled=True,
        jwt_hmac_secret=None,
        jwt_public_keys_pem=None,
        dashboard_session_cookie_name="ibex_session",
    )
    req.cookies = {"ibex_session": "x"}
    with pytest.raises(ApiError) as exc:
        _require_operator_session(req)
    assert "session signing secret" in str(exc.value)


def test_require_session_verify_ok() -> None:
    req = _authed_request()
    claims = _claims()
    with patch.object(platform_mod, "verify_token_opts", return_value=claims) as verify:
        got = _require_operator_session(req)
    assert got is claims
    verify.assert_called_once()


def test_require_session_permissions_zero() -> None:
    req = _authed_request()
    claims = _claims(permissions=0)
    with (
        patch.object(platform_mod, "verify_token_opts", return_value=claims),
        pytest.raises(ApiError) as exc,
    ):
        _require_operator_session(req)
    assert exc.value.code == INSUFFICIENT_PERMISSIONS


def test_require_session_verify_fails() -> None:
    from app.session_stub import SessionStubError

    req = _authed_request()
    with (
        patch.object(
            platform_mod, "verify_token_opts", side_effect=SessionStubError("bad token")
        ),
        pytest.raises(ApiError) as exc,
    ):
        _require_operator_session(req)
    assert exc.value.code == INVALID_TOKEN


@pytest.mark.asyncio
async def test_outbox_watermark_none_session() -> None:
    assert await platform_mod._outbox_watermark(None) is None


@pytest.mark.asyncio
async def test_outbox_watermark_query_error() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("boom"))
    assert await platform_mod._outbox_watermark(session) is None


@pytest.mark.asyncio
async def test_platform_health_outbox_factory_raises() -> None:
    req = _authed_request()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=[RuntimeError("db"), RuntimeError("db2")])
    cm.__aexit__ = AsyncMock(return_value=None)
    req.app.state.api.session_factory = MagicMock(return_value=cm)
    with (
        patch.object(platform_mod, "_require_operator_session", return_value=_claims()),
        patch.object(platform_mod, "_redis_status", AsyncMock(return_value="ok")),
    ):
        out = await platform_health(req)
    assert out.outbox_max_aggregate_seq is None
    assert out.dependency_health["postgres"] == "unavailable"


@pytest.mark.asyncio
async def test_auth_status_timeout() -> None:
    validator = MagicMock()
    validator.ready = AsyncMock(side_effect=TimeoutError())
    assert await platform_mod._auth_status(validator) == "unavailable"


@pytest.mark.asyncio
async def test_redis_status_no_url() -> None:
    assert await platform_mod._redis_status(None) == "unavailable"
