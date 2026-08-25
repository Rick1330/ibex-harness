"""Application runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from app.audit import AsyncAuditEmitter
from app.auth import TokenValidator


@dataclass
class AppState:
    ready: bool = False
    ready_error: str | None = None
    validator: TokenValidator | None = None
    audit: AsyncAuditEmitter | None = None
    mcp_app: object | None = None
