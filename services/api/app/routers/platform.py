"""Operator platform health surface for Overview (4.P.5 → 4.D.1).

Exposes dependency health, last backup, last restore-drill result, retention
horizon, ingestion lag, DLQ depth, and degraded-mode state — matching the
operator-platform research contract consumed by 4.D.1 Overview.

Auth: provisional dashboard session cookie + OPERATOR_METADATA_READ.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from apierror_py import INVALID_TOKEN, SERVICE_DEGRADED
from authclient.permissions import OPERATOR_METADATA_READ
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import assert_operator_permission
from app.db import session_with_org
from app.errors import ApiError
from app.session_stub import (
    SESSION_KIND_ACCESS,
    SessionClaims,
    SessionStubError,
    TokenVerifyOpts,
    verify_token_opts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/operator/platform", tags=["operator-platform"])

_DEFAULT_RETENTION_DAYS = 90
_DEP_TIMEOUT_SEC = 2.0
# Bandit B108: prefer durable operator state dir over world-writable /tmp.
_BACKUP_STAMP = Path(
    os.environ.get("IBEX_LAST_BACKUP_STAMP", "/var/lib/ibex/backup/last-backup.txt")
)
_DRILL_REPORT = Path(
    os.environ.get(
        "RESTORE_DRILL_REPORT",
        "/var/lib/ibex/restore-drill/restore-drill-report.json",
    )
)


class PlatformHealthResponse(BaseModel):
    dependency_health: dict[str, str] = Field(
        description="ok|degraded|unavailable per dependency"
    )
    last_backup_at: datetime | None = None
    last_restore_drill: dict[str, Any] | None = None
    retention_horizon_days: int = _DEFAULT_RETENTION_DAYS
    ingestion_lag_seconds: float | None = None
    dlq_depth: int | None = None
    degraded_mode: bool = False
    outbox_max_aggregate_seq: int | None = None
    deploy_image_digest: str | None = None
    observed_at: datetime


def _settings(request: Request) -> Any:
    return request.app.state.settings


def _assert_feature_and_secret(settings: Any) -> None:
    if not getattr(settings, "operator_feature_enabled", False):
        raise ApiError(code=SERVICE_DEGRADED, message="operator feature disabled")
    if not settings.jwt_hmac_secret and not settings.jwt_public_keys_pem:
        raise ApiError(code=SERVICE_DEGRADED, message="session signing secret not configured")


def _access_cookie(request: Request, settings: Any) -> str:
    raw = request.cookies.get(settings.dashboard_session_cookie_name)
    if not raw:
        raise ApiError(code=INVALID_TOKEN, message="missing session cookie")
    return raw


def _verify_access_cookie(raw: str, settings: Any) -> SessionClaims:
    try:
        return verify_token_opts(
            raw,
            TokenVerifyOpts(
                secret=settings.jwt_hmac_secret,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                expect_kind=SESSION_KIND_ACCESS,
                public_keys_pem=settings.jwt_public_keys_pem,
            ),
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc


def _require_operator_session(request: Request) -> SessionClaims:
    """Fail closed: feature flag + access cookie + OPERATOR_METADATA_READ."""
    settings = _settings(request)
    _assert_feature_and_secret(settings)
    claims = _verify_access_cookie(_access_cookie(request, settings), settings)
    assert_operator_permission(settings, claims.permissions, OPERATOR_METADATA_READ)
    return claims


async def _postgres_status(session_factory: Any) -> str:
    if session_factory is None:
        return "unavailable"
    try:
        async with session_factory() as session:  # type: ignore[misc]
            await session.execute(text("SELECT 1"))
        return "ok"
    except (SQLAlchemyError, OSError, RuntimeError):
        return "unavailable"


async def _auth_status(validator: Any) -> str:
    if validator is None:
        return "unavailable"
    ready = getattr(validator, "ready", None)
    if ready is None:
        return "unavailable"
    try:
        ok = await asyncio.wait_for(ready(), timeout=_DEP_TIMEOUT_SEC)
        return "ok" if ok else "unavailable"
    except (OSError, RuntimeError):
        # TimeoutError is an OSError subclass on CPython 3.x (Sonar redundant catch).
        return "unavailable"


async def _redis_status(redis_url: str | None) -> str:
    if not redis_url:
        return "unavailable"
    try:
        from redis.asyncio import Redis
        from redis.exceptions import RedisError
    except ImportError:
        return "unavailable"
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=_DEP_TIMEOUT_SEC,
            socket_timeout=_DEP_TIMEOUT_SEC,
        )
        try:
            pong = await asyncio.wait_for(client.ping(), timeout=_DEP_TIMEOUT_SEC)
            return "ok" if pong else "unavailable"
        finally:
            await client.aclose()
    except (OSError, RuntimeError, RedisError):
        return "unavailable"


async def _dep_health(request: Request) -> dict[str, str]:
    state = request.app.state.api
    settings = _settings(request)
    out: dict[str, str] = {
        "api": "ok" if getattr(state, "ready", False) else "unavailable",
        "postgres": await _postgres_status(getattr(state, "session_factory", None)),
        "auth": await _auth_status(getattr(state, "validator", None)),
        "redis": await _redis_status(getattr(settings, "redis_url", None)),
    }
    return out


def _parse_backup_stamp() -> datetime | None:
    try:
        if not _BACKUP_STAMP.exists():
            return None
        raw = _BACKUP_STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    parts = raw.rsplit(" ", 1)
    candidate = parts[-1] if parts else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _load_drill() -> dict[str, Any] | None:
    try:
        if not _DRILL_REPORT.exists():
            return None
        parsed = json.loads(_DRILL_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _outbox_watermark(session: AsyncSession | None, org_id: UUID) -> int | None:
    if session is None:
        return None
    try:
        row = await session.execute(
            text(
                "SELECT COALESCE(MAX(aggregate_seq), 0) FROM ibex_core.evidence_outbox "
                "WHERE org_id = CAST(:org_id AS uuid)"
            ),
            {"org_id": str(org_id)},
        )
        return int(row.scalar_one())
    except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("outbox watermark unavailable", exc_info=True)
        return None


def _parse_dlq_depth() -> int | None:
    raw = os.environ.get("IBEX_DLQ_DEPTH")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@router.get("/health")
async def platform_health(request: Request) -> PlatformHealthResponse:
    """Read-only platform freshness for operator Overview (4.D.1 consumer)."""
    claims = _require_operator_session(request)

    deps = await _dep_health(request)
    drain = getattr(request.app.state.api, "drain", None)
    draining = bool(drain is not None and getattr(drain, "is_draining", lambda: False)())
    degraded = any(v != "ok" for v in deps.values()) or draining

    session_factory = getattr(request.app.state.api, "session_factory", None)
    outbox_seq: int | None = None
    if session_factory is not None:
        try:
            async with session_with_org(session_factory, str(claims.org_id)) as session:
                outbox_seq = await _outbox_watermark(session, claims.org_id)
        except (SQLAlchemyError, OSError, RuntimeError):
            outbox_seq = None

    last_backup, last_drill = await asyncio.gather(
        asyncio.to_thread(_parse_backup_stamp),
        asyncio.to_thread(_load_drill),
    )

    return PlatformHealthResponse(
        dependency_health=deps,
        last_backup_at=last_backup,
        last_restore_drill=last_drill,
        retention_horizon_days=int(
            getattr(_settings(request), "platform_retention_horizon_days", _DEFAULT_RETENTION_DAYS)
        ),
        ingestion_lag_seconds=None,  # residual: wire CH ingestion lag in 4.D.1
        dlq_depth=_parse_dlq_depth(),
        degraded_mode=degraded,
        outbox_max_aggregate_seq=outbox_seq,
        deploy_image_digest=os.environ.get("IBEX_DEPLOY_IMAGE_DIGEST") or None,
        observed_at=datetime.now(UTC),
    )
