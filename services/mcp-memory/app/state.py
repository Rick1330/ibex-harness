"""Application runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from app.audit import AsyncAuditEmitter
from app.auth import TokenValidator
from app.clients.memory import MemoryHttpClient
from app.ratelimit import McpRateLimiter


@dataclass
class AppState:
    ready: bool = False
    ready_error: str | None = None
    validator: TokenValidator | None = None
    audit: AsyncAuditEmitter | None = None
    memory_client: MemoryHttpClient | None = None
    rate_limiter: McpRateLimiter | None = None
    mcp_app: object | None = None
