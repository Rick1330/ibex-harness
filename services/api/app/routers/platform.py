"""Operator platform health surface for Overview (4.P.5 → 4.D.1).

Exposes dependency health, last backup, last restore-drill result, retention
horizon, ingestion lag, DLQ depth, and degraded-mode state — matching the
operator-platform research contract consumed by 4.D.1 Overview.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apierror_py import SERVICE_DEGRADED
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/operator/platform", tags=["operator-platform"])

_DEFAULT_RETENTION_DAYS = 90
_BACKUP_STAMP = Path("/tmp/ibex-last-backup.txt")
_DRILL_REPORT = Path(
    os.environ.get("RESTORE_DRILL_REPORT", "/tmp/ibex-restore-drill/restore-drill-report.json")
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


async def _dep_health(request: Request) -> dict[str, str]:
    state = request.app.state.api
    out: dict[str, str] = {"api": "ok" if getattr(state, "ready", False) else "unavailable"}
    session_factory = getattr(state, "session_factory", None)
    if session_factory is None:
        out["postgres"] = "unavailable"
    else:
        try:
            async with session_factory() as session:  # type: ignore[misc]
                await session.execute(text("SELECT 1"))
            out["postgres"] = "ok"
        except (SQLAlchemyError, OSError, RuntimeError):
            out["postgres"] = "unavailable"
    out["auth"] = "ok" if getattr(state, "validator", None) is not None else "unavailable"
    out["redis"] = "ok" if getattr(_settings(request), "redis_url", None) else "unavailable"
    return out


def _parse_backup_stamp() -> datetime | None:
    if not _BACKUP_STAMP.exists():
        return None
    raw = _BACKUP_STAMP.read_text(encoding="utf-8").strip()
    # "[backup] ok 2026-09-19T07:00:00Z"
    parts = raw.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    try:
        return datetime.fromisoformat(parts[1])
    except ValueError:
        return None


def _load_drill() -> dict[str, Any] | None:
    if not _DRILL_REPORT.exists():
        return None
    try:
        return json.loads(_DRILL_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


async def _outbox_watermark(session: AsyncSession | None) -> int | None:
    if session is None:
        return None
    try:
        row = await session.execute(
            text("SELECT COALESCE(MAX(aggregate_seq), 0) FROM ibex_core.evidence_outbox")
        )
        return int(row.scalar_one())
    except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError):
        logger.debug("outbox watermark unavailable", exc_info=True)
        return None


@router.get("/health", response_model=PlatformHealthResponse)
async def platform_health(request: Request) -> PlatformHealthResponse:
    """Read-only platform freshness for operator Overview (4.D.1 consumer)."""
    settings = _settings(request)
    if not getattr(settings, "operator_feature_enabled", False):
        raise ApiError(code=SERVICE_DEGRADED, message="operator feature disabled")

    deps = await _dep_health(request)
    drain = getattr(request.app.state.api, "drain", None)
    draining = bool(drain is not None and getattr(drain, "is_draining", lambda: False)())
    degraded = any(v != "ok" for v in deps.values()) or draining

    session_factory = getattr(request.app.state.api, "session_factory", None)
    outbox_seq: int | None = None
    if session_factory is not None:
        try:
            async with session_factory() as session:  # type: ignore[misc]
                outbox_seq = await _outbox_watermark(session)
        except (SQLAlchemyError, OSError, RuntimeError):
            outbox_seq = None

    dlq: int | None = None
    raw_dlq = os.environ.get("IBEX_DLQ_DEPTH")
    if raw_dlq is not None:
        try:
            dlq = int(raw_dlq)
        except ValueError:
            dlq = None

    return PlatformHealthResponse(
        dependency_health=deps,
        last_backup_at=_parse_backup_stamp(),
        last_restore_drill=_load_drill(),
        retention_horizon_days=int(
            getattr(settings, "platform_retention_horizon_days", _DEFAULT_RETENTION_DAYS)
        ),
        ingestion_lag_seconds=None,
        dlq_depth=dlq,
        degraded_mode=degraded,
        outbox_max_aggregate_seq=outbox_seq,
        deploy_image_digest=os.environ.get("IBEX_DEPLOY_IMAGE_DIGEST") or None,
        observed_at=datetime.now(UTC),
    )
