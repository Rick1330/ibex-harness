"""HTTP helpers for POST /v1/memories (idempotency + error mapping)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.idempotency.redis_store import ClaimKind, ClaimOutcome, IdempotencyToken
from app.schemas.limits import MAX_IDEMPOTENCY_KEY_LENGTH


class IdempotencyHandle:
    """Claim state for a single create-memory request."""

    __slots__ = ("fingerprint", "store", "token")

    def __init__(
        self,
        *,
        store: object | None,
        token: IdempotencyToken | None,
        fingerprint: str,
    ) -> None:
        self.store = store
        self.token = token
        self.fingerprint = fingerprint

    @property
    def active(self) -> bool:
        return self.token is not None and self.store is not None


def parse_idempotency_key(raw: str | None) -> str | None:
    """Validate X-Idempotency-Key before it is used in Redis keys."""
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": (
                    f"X-Idempotency-Key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters"
                ),
            },
        )
    return key


async def begin_idempotency(
    *,
    store: object | None,
    org_id: UUID,
    idempotency_key: str | None,
    fingerprint: str,
) -> IdempotencyHandle | JSONResponse:
    handle = IdempotencyHandle(store=store, token=None, fingerprint=fingerprint)
    validated_key = parse_idempotency_key(idempotency_key)
    if not validated_key or store is None:
        return handle
    handle.token = IdempotencyToken(org_id=org_id, key=validated_key)
    claim: ClaimOutcome = await store.claim(handle.token, fingerprint)
    if claim.kind == ClaimKind.HIT and claim.record is not None:
        return JSONResponse(
            status_code=claim.record.status,
            content=json.loads(claim.record.body.decode("utf-8")),
            headers={"X-Idempotency-Replayed": "true"},
        )
    if claim.kind == ClaimKind.CONFLICT:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_CONFLICT",
                "message": "Idempotency key reused with different request",
            },
        )
    if claim.kind == ClaimKind.IN_PROGRESS:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_IN_PROGRESS",
                "message": "Request with this idempotency key is in progress",
            },
        )
    return handle


async def release_idempotency(handle: IdempotencyHandle) -> None:
    if handle.active:
        await handle.store.release(handle.token, handle.fingerprint)


async def commit_idempotency(handle: IdempotencyHandle, *, status: int, body: bytes) -> None:
    if handle.active:
        await handle.store.commit(
            handle.token,
            fingerprint=handle.fingerprint,
            status=status,
            body=body,
        )


def http_error_for_write(exc: BaseException) -> HTTPException:
    if isinstance(exc, DuplicateMemoryError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_CONTENT",
                "message": "A memory with identical content already exists",
                "existing_memory_id": str(exc.existing_id),
            },
        )
    if isinstance(exc, ValidationError):
        return HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, EmbeddingServiceError):
        return HTTPException(
            status_code=503,
            detail={"code": "EMBEDDING_FAILED", "message": "Embedding service unavailable"},
        )
    raise exc
