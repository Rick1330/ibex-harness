"""FastAPI dependencies for the management API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from apierror_py import (
    AUTH_UNAVAILABLE,
    INVALID_TOKEN,
    MISSING_TOKEN,
    ORG_SUSPENDED,
    SERVICE_DEGRADED,
)
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import TokenValidator, ValidateResult, parse_authorization_header
from app.auth.errors import AuthFailedError, AuthUnavailableError, OrgSuspendedError
from app.db import session_with_org
from app.errors import ApiError


def _require_api_component(request: Request, attr: str, *, message: str):
    value = getattr(request.app.state.api, attr, None)
    if value is None:
        raise ApiError(code=SERVICE_DEGRADED, message=message)
    return value


def get_validator(request: Request) -> TokenValidator:
    return _require_api_component(request, "validator", message="Auth not configured")


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return _require_api_component(
        request, "session_factory", message="Database not configured"
    )


async def require_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    validator: Annotated[TokenValidator, Depends(get_validator)] = None,  # type: ignore[assignment]
) -> ValidateResult:
    try:
        token_value = parse_authorization_header(authorization)
        return await validator.validate(token_value)
    except OrgSuspendedError as exc:
        raise ApiError(code=ORG_SUSPENDED, message=str(exc)) from exc
    except AuthFailedError as exc:
        code = MISSING_TOKEN if "missing" in str(exc).lower() else INVALID_TOKEN
        raise ApiError(code=code, message=str(exc)) from exc
    except AuthUnavailableError as exc:
        raise ApiError(
            code=AUTH_UNAVAILABLE,
            message="Authentication unavailable",
        ) from exc


async def org_session(
    token: Annotated[ValidateResult, Depends(require_token)],
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """Request-scoped DB session with ``app.current_org_id`` set from the token."""
    async with session_with_org(factory, str(token.org_id)) as session:
        yield session


def org_id_from_token(token: Annotated[ValidateResult, Depends(require_token)]) -> UUID:
    return token.org_id
