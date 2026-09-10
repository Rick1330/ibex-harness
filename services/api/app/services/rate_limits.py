"""Org/agent RPM override persistence + effective-limit reads (m4.B.2)."""

from __future__ import annotations

import logging
from uuid import UUID

from apierror_py import NOT_FOUND, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import AGENT_NOT_FOUND_MSG
from app.errors import ApiError
from app.rate_limit_publish import (
    NoopRateLimitConfigPublisher,
    RateLimitConfigPublisher,
    RedisRateLimitCounter,
)
from app.schemas.rate_limits import (
    AgentRateLimitView,
    RateLimitsPatchRequest,
    RateLimitsResponse,
)

logger = logging.getLogger(__name__)

_LIST_OVERRIDES_SQL = """
SELECT agent_id, requests_per_minute
FROM ibex_core.rate_limit_overrides
WHERE org_id = :org_id
"""

_UPSERT_ORG_SQL = """
INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
VALUES (:org_id, NULL, :rpm)
ON CONFLICT (org_id) WHERE agent_id IS NULL
DO UPDATE SET requests_per_minute = EXCLUDED.requests_per_minute,
              updated_at = now()
"""

_DELETE_ORG_SQL = """
DELETE FROM ibex_core.rate_limit_overrides
WHERE org_id = :org_id AND agent_id IS NULL
"""

_UPSERT_AGENT_SQL = """
INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
VALUES (:org_id, :agent_id, :rpm)
ON CONFLICT (org_id, agent_id)
DO UPDATE SET requests_per_minute = EXCLUDED.requests_per_minute,
              updated_at = now()
"""

_DELETE_AGENT_SQL = """
DELETE FROM ibex_core.rate_limit_overrides
WHERE org_id = :org_id AND agent_id = :agent_id
"""

_AGENT_EXISTS_SQL = """
SELECT 1
FROM ibex_core.agents
WHERE id = :agent_id AND org_id = :org_id AND deleted_at IS NULL
"""


async def get_rate_limits(
    session: AsyncSession,
    org_id: UUID,
    *,
    platform_default_rpm: int,
    counter: RedisRateLimitCounter,
) -> RateLimitsResponse:
    rows = await session.execute(text(_LIST_OVERRIDES_SQL), {"org_id": str(org_id)})
    org_rpm: int | None = None
    agents: list[AgentRateLimitView] = []
    for agent_id, rpm in rows.all():
        if agent_id is None:
            org_rpm = int(rpm)
            continue
        agents.append(
            AgentRateLimitView(
                agent_id=agent_id if isinstance(agent_id, UUID) else UUID(str(agent_id)),
                requests_per_minute=int(rpm),
                source="override",
            )
        )
    agents.sort(key=lambda a: str(a.agent_id))
    effective = org_rpm if org_rpm is not None else platform_default_rpm
    current = await counter.org_current_minute_requests(str(org_id))
    return RateLimitsResponse(
        org_id=org_id,
        requests_per_minute=effective,
        source="override" if org_rpm is not None else "default",
        platform_default_rpm=platform_default_rpm,
        current_minute_requests=current,
        agent_overrides=agents,
    )


async def patch_rate_limits(
    session: AsyncSession,
    org_id: UUID,
    body: RateLimitsPatchRequest,
    *,
    platform_default_rpm: int,
    counter: RedisRateLimitCounter,
    publisher: RateLimitConfigPublisher | None,
) -> RateLimitsResponse:
    if body.clear_org_override and body.requests_per_minute is not None:
        raise ApiError(
            code=VALIDATION_ERROR,
            message="clear_org_override cannot be combined with requests_per_minute",
        )
    if body.clear_org_override:
        await session.execute(text(_DELETE_ORG_SQL), {"org_id": str(org_id)})
    elif body.requests_per_minute is not None:
        await session.execute(
            text(_UPSERT_ORG_SQL),
            {"org_id": str(org_id), "rpm": body.requests_per_minute},
        )

    for item in body.agent_overrides:
        await _ensure_agent_in_org(session, org_id, item.agent_id)
        if item.requests_per_minute is None:
            await session.execute(
                text(_DELETE_AGENT_SQL),
                {"org_id": str(org_id), "agent_id": str(item.agent_id)},
            )
        else:
            await session.execute(
                text(_UPSERT_AGENT_SQL),
                {
                    "org_id": str(org_id),
                    "agent_id": str(item.agent_id),
                    "rpm": item.requests_per_minute,
                },
            )

    await session.flush()
    await session.commit()

    pub = publisher or NoopRateLimitConfigPublisher()
    try:
        await pub.publish_config_update(str(org_id))
    except Exception as exc:  # noqa: BLE001 — never roll back PG on publish failure
        logger.warning(
            "rate-limit config publish failed; poll will converge org_id=%s error_class=%s",
            org_id,
            type(exc).__name__,
        )

    return await get_rate_limits(
        session,
        org_id,
        platform_default_rpm=platform_default_rpm,
        counter=counter,
    )


async def _ensure_agent_in_org(
    session: AsyncSession, org_id: UUID, agent_id: UUID
) -> None:
    result = await session.execute(
        text(_AGENT_EXISTS_SQL),
        {"org_id": str(org_id), "agent_id": str(agent_id)},
    )
    if result.scalar_one_or_none() is None:
        raise ApiError(code=NOT_FOUND, message=AGENT_NOT_FOUND_MSG)
