"""ASGI bearer auth middleware for the MCP operator surface (fail closed).

Pure ASGI — ``BaseHTTPMiddleware`` breaks Streamable HTTP streaming. The validator
is resolved via a provider so it can be wired during lifespan.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from mcp_gateway import GatewayPrincipal, ToolAuditEvent
from mcp_runtime.middleware import (
    AUTH_AUDIT_ORG_UNKNOWN,
    origin_from_resource,
    path_is_protected,
)
from mcp_runtime.middleware import (
    BearerAuthConfig as SharedBearerAuthConfig,
)
from mcp_runtime.middleware import (
    BearerAuthMiddleware as _BearerAuthMiddleware,
)
from starlette.types import ASGIApp

from app.audit import AsyncAuditEmitter
from app.auth import TokenValidator, parse_authorization_header
from app.config import Settings
from app.errors import AuthFailedError, AuthUnavailableError
from app.principal import set_principal

ValidatorProvider = Callable[[], TokenValidator | None]
AuditProvider = Callable[[], AsyncAuditEmitter | None]

# Backwards-compatible aliases for existing tests and imports.
_origin_from_resource = origin_from_resource
_path_is_protected = path_is_protected


@dataclass(frozen=True, slots=True)
class BearerAuthConfig:
    settings: Settings
    get_validator: ValidatorProvider
    get_audit: AuditProvider | None = None
    protected_prefixes: tuple[str, ...] = ("/mcp",)


class BearerAuthMiddleware(_BearerAuthMiddleware):
    """Validates the bearer token and binds a token-derived principal."""

    def __init__(self, app: ASGIApp, config: BearerAuthConfig) -> None:
        super().__init__(app, _shared_config(config))


def _shared_config(config: BearerAuthConfig) -> SharedBearerAuthConfig[GatewayPrincipal]:
    return SharedBearerAuthConfig(
        realm="ibex-mcp-operator",
        resource_url=config.settings.resource_url,
        get_validator=config.get_validator,
        parse_token=parse_authorization_header,
        bind_principal=lambda _token, principal: set_principal(principal),
        clear_principal=lambda: set_principal(None),
        auth_failed_error=AuthFailedError,
        auth_unavailable_error=AuthUnavailableError,
        emit_deny=_deny_emitter(config.get_audit or (lambda: None)),
        protected_prefixes=config.protected_prefixes,
    )


def _deny_emitter(get_audit: AuditProvider) -> Callable[[str, int], None]:
    def emit(error_code: str, latency_ms: int) -> None:
        audit = get_audit()
        if audit is None:
            return
        audit.emit(
            ToolAuditEvent(
                request_id=str(uuid.uuid4()),
                org_id=AUTH_AUDIT_ORG_UNKNOWN,
                tool_name="auth",
                decision="deny",
                success=False,
                error_code=error_code,
                latency_ms=latency_ms,
            )
        )

    return emit
