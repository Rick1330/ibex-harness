"""Shared factories for memory write unit tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.idempotency.redis_store import IdempotencyToken
from app.routers.memory_write_support import IdempotencyHandle
from app.write.models import MemoryRow


def sample_memory_row(**overrides: object) -> MemoryRow:
    now = datetime.now(tz=UTC)
    row = MemoryRow(
        id=uuid4(),
        org_id=uuid4(),
        agent_id=uuid4(),
        content="hello",
        content_tokens=1,
        category="factual",
        confidence=0.8,
        status="active",
        source="user_provided",
        pii_detected=False,
        pii_redacted=False,
        session_id=None,
        visibility="agent",
        pinned=False,
        tags=(),
        metadata={},
        retrieval_count=0,
        usefulness_score=0.5,
        valid_from=now,
        valid_until=None,
        created_at=now,
        updated_at=now,
    )
    if overrides:
        return replace(row, **overrides)  # type: ignore[arg-type]
    return row


def mock_async_session_factory() -> MagicMock:
    """Async session factory with begin() context manager for orchestrator tests."""
    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_cm)


def mapping_row(**overrides: object) -> SimpleNamespace:
    org_id = uuid4()
    agent_id = uuid4()
    now = datetime.now(tz=UTC)
    base = {
        "id": uuid4(),
        "org_id": org_id,
        "agent_id": agent_id,
        "content": "hello world",
        "content_tokens": 2,
        "category": "factual",
        "confidence": 0.8,
        "status": "active",
        "source": "user_provided",
        "pii_detected": False,
        "pii_redacted": False,
        "session_id": None,
        "metadata": "{}",
        "retrieval_count": 0,
        "usefulness_score": 0.5,
        "valid_from": now,
        "valid_until": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def active_idempotency_handle(*, store: MagicMock | None = None) -> IdempotencyHandle:
    return IdempotencyHandle(
        store=store or MagicMock(),
        token=IdempotencyToken(org_id=uuid4(), key="k"),
        fingerprint="fp",
    )


@dataclass(frozen=True, slots=True)
class HashViolationOpts:
    sqlstate: str | None = "23505"
    pgcode: str | None = None
    constraint_name: str = ""
    detail: str = ""
    message: str = (
        'duplicate key value violates unique constraint '
        '"idx_memories_org_agent_content_hash_active"'
    )


@dataclass(frozen=True, slots=True)
class LabelViolationOpts:
    constraint_name: str = "memory_labels_pkey"
    message: str = 'duplicate key value violates unique constraint "memory_labels_pkey"'


def mock_session_returning_row(row: SimpleNamespace) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = row
    session.execute = AsyncMock(return_value=result)
    return session


def hash_violation_integrity_error(
    opts: HashViolationOpts | None = None,
) -> IntegrityError:
    cfg = opts or HashViolationOpts()
    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = cfg.sqlstate
    orig.pgcode = cfg.pgcode
    orig.constraint_name = cfg.constraint_name
    orig.diag = None
    orig.detail = cfg.detail
    orig.__str__ = lambda self: cfg.message
    exc.orig = orig
    return exc


def label_violation_integrity_error(
    opts: LabelViolationOpts | None = None,
) -> IntegrityError:
    cfg = opts or LabelViolationOpts()
    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.constraint_name = cfg.constraint_name
    orig.__str__ = lambda self: cfg.message
    exc.orig = orig
    return exc
