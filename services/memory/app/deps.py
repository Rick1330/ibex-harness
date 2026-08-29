"""FastAPI dependencies for memory write API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import TokenValidator, ValidateResult, parse_authorization_header
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.permissions import MEMORY_READ, MEMORY_WRITE, has_permission
from app.read.repository import MemoryReadRepository
from app.write.orchestrator import MemoryWriteOrchestrator

_T = TypeVar("_T")


def _require_memory_component(
    request: Request,
    attr: str,
    *,
    message: str,
) -> _T:
    value = getattr(request.app.state.memory, attr, None)
    if value is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_DEGRADED", "message": message},
        )
    return value


def _optional_memory_component(request: Request, attr: str) -> object | None:
    return getattr(request.app.state.memory, attr, None)


def get_validator(request: Request) -> TokenValidator:
    return _require_memory_component(request, "validator", message="Auth not configured")


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return _require_memory_component(
        request, "session_factory", message="Database not configured"
    )


def get_write_orchestrator(request: Request) -> MemoryWriteOrchestrator:
    return _require_memory_component(
        request, "write_orchestrator", message="Write path not configured"
    )


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


def _require_memory_permission(
    token: ValidateResult,
    permission: int,
    label: str,
) -> ValidateResult:
    if not has_permission(token.permissions, permission):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_PERMISSIONS",
                "message": f"Permission required: {label}",
            },
        )
    return token


def require_memory_write(
    token: Annotated[ValidateResult, Depends(require_token)],
) -> ValidateResult:
    return _require_memory_permission(token, MEMORY_WRITE, "memory:write")


def require_memory_read(
    token: Annotated[ValidateResult, Depends(require_token)],
) -> ValidateResult:
    return _require_memory_permission(token, MEMORY_READ, "memory:read")


def get_read_repository(request: Request) -> MemoryReadRepository:
    return _require_memory_component(
        request, "read_repository", message="Read path not configured"
    )


def get_embedding_client(request: Request):
    return _require_memory_component(
        request, "embedding_client", message="Embedding client not configured"
    )


def get_idempotency_store(request: Request):
    return _optional_memory_component(request, "idempotency_store")


def get_redis(request: Request):
    return _optional_memory_component(request, "redis")


@dataclass(frozen=True, slots=True)
class CreateMemoryContext:
    token: ValidateResult
    orchestrator: MemoryWriteOrchestrator
    idempotency_store: object | None
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class SearchMemoryContext:
    token: ValidateResult
    read_repository: MemoryReadRepository
    embedding_client: object
    session_factory: async_sessionmaker[AsyncSession]


def get_search_memory_context(
    token: Annotated[ValidateResult, Depends(require_memory_read)],
    read_repository: Annotated[MemoryReadRepository, Depends(get_read_repository)],
    embedding_client: Annotated[object, Depends(get_embedding_client)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> SearchMemoryContext:
    return SearchMemoryContext(
        token=token,
        read_repository=read_repository,
        embedding_client=embedding_client,
        session_factory=session_factory,
    )


def get_create_memory_context(
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
