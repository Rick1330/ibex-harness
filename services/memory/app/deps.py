"""FastAPI dependencies for memory write API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import TokenValidator, ValidateResult, parse_authorization_header
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.permissions import MEMORY_WRITE, has_permission
from app.write.orchestrator import MemoryWriteOrchestrator


def get_validator(request: Request) -> TokenValidator:
    validator = getattr(request.app.state.memory, "validator", None)
    if validator is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_DEGRADED", "message": "Auth not configured"},
        )
    return validator


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = getattr(request.app.state.memory, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_DEGRADED", "message": "Database not configured"},
        )
    return factory


def get_write_orchestrator(request: Request) -> MemoryWriteOrchestrator:
    orchestrator = getattr(request.app.state.memory, "write_orchestrator", None)
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_DEGRADED", "message": "Write path not configured"},
        )
    return orchestrator


async def require_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    validator: Annotated[TokenValidator, Depends(get_validator)] = None,
) -> ValidateResult:
    try:
        token_value = parse_authorization_header(authorization)
        return await validator.validate(token_value)
    except AuthFailedError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_TOKEN", "message": str(exc)},
        ) from exc
    except AuthUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_DEGRADED", "message": "Authentication unavailable"},
        ) from exc


def require_memory_write(
    token: Annotated[ValidateResult, Depends(require_token)],
) -> ValidateResult:
    if not has_permission(token.permissions, MEMORY_WRITE):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_PERMISSIONS",
                "message": "Permission required: memory:write",
            },
        )
    return token


def get_idempotency_store(request: Request):
    return getattr(request.app.state.memory, "idempotency_store", None)


def get_redis(request: Request):
    return getattr(request.app.state.memory, "redis", None)


@dataclass(frozen=True, slots=True)
class CreateMemoryContext:
    token: ValidateResult
    orchestrator: MemoryWriteOrchestrator
    idempotency_store: object | None
    idempotency_key: str | None


async def get_create_memory_context(
    token: Annotated[ValidateResult, Depends(require_memory_write)],
    orchestrator: Annotated[MemoryWriteOrchestrator, Depends(get_write_orchestrator)],
    idempotency_store: Annotated[object | None, Depends(get_idempotency_store)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CreateMemoryContext:
    return CreateMemoryContext(
        token=token,
        orchestrator=orchestrator,
        idempotency_store=idempotency_store,
        idempotency_key=idempotency_key,
    )
