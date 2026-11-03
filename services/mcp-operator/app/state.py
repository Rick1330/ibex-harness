"""Application runtime state for the operator gateway."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.audit import AsyncAuditEmitter
from app.auth import TokenValidator
from app.ratelimit import OperatorRateLimiter


@dataclass
class AppState:
    ready: bool = False
    ready_error: str | None = None
    enabled: bool = False
    validator: TokenValidator | None = None
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    rate_limiter: OperatorRateLimiter | None = None
    audit: AsyncAuditEmitter | None = None
    mcp_app: object | None = None
