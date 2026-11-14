"""Shared factories for memory write unit tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ibex_idempotency import ClaimToken, LedgerValidationError
from sqlalchemy.exc import IntegrityError

from app.routers.memory_write_idempotency import IdempotencyHandle
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


def active_idempotency_handle(*, ledger: MagicMock | None = None) -> IdempotencyHandle:
    return IdempotencyHandle(
        ledger=ledger or MagicMock(),
        claim=ClaimToken(
            claim_id=uuid4(),
            org_id=uuid4(),
            agent_id=uuid4(),
            key="k",
            request_hash="f" * 64,
            version=1,
        ),
        request_hash="f" * 64,
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


@dataclass(frozen=True, slots=True)
class AgentFkViolationOpts:
    sqlstate: str | None = "23503"
    pgcode: str | None = None
    constraint_name: str = "memories_agent_org_fk"
    message: str = (
        'insert or update on table "memories" violates foreign key constraint '
        '"memories_agent_org_fk"'
    )


def mock_session_returning_row(row: SimpleNamespace) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = row
    session.execute = AsyncMock(return_value=result)
    return session


def _integrity_error(
    *,
    message: str,
    sqlstate: str | None = None,
    pgcode: str | None = None,
    constraint_name: str = "",
) -> IntegrityError:
    """Build an IntegrityError whose ``orig`` carries driver-style attributes."""
    exc = IntegrityError("insert", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = sqlstate
    orig.pgcode = pgcode
    orig.constraint_name = constraint_name
    orig.diag = None
    orig.detail = ""
    orig.__str__ = lambda self: message
    exc.orig = orig
    return exc


def hash_violation_integrity_error(
    opts: HashViolationOpts | None = None,
) -> IntegrityError:
    cfg = opts or HashViolationOpts()
    exc = _integrity_error(
        message=cfg.message,
        sqlstate=cfg.sqlstate,
        pgcode=cfg.pgcode,
        constraint_name=cfg.constraint_name,
    )
    exc.orig.detail = cfg.detail
    return exc


def label_violation_integrity_error(
    opts: LabelViolationOpts | None = None,
) -> IntegrityError:
    cfg = opts or LabelViolationOpts()
    return _integrity_error(message=cfg.message, constraint_name=cfg.constraint_name)


def agent_fk_violation_integrity_error(
    opts: AgentFkViolationOpts | None = None,
) -> IntegrityError:
    """IntegrityError shaped like a memories -> agents composite-FK violation."""
    cfg = opts or AgentFkViolationOpts()
    return _integrity_error(
        message=cfg.message,
        sqlstate=cfg.sqlstate,
        pgcode=cfg.pgcode,
        constraint_name=cfg.constraint_name,
    )


@dataclass(frozen=True, slots=True)
class LedgerFkViolationOpts:
    sqlstate: str | None = "23503"
    constraint_name: str = "idempotency_ledger_agent_id_fkey"
    message: str = (
        'insert or update on table "idempotency_ledger" violates foreign key constraint '
        '"idempotency_ledger_agent_id_fkey"'
    )


def ledger_validation_error(
    opts: LedgerFkViolationOpts | None = None,
) -> LedgerValidationError:
    """LedgerValidationError shaped like the ledger's own claim rejection.

    ``PostgresIdempotencyLedger.claim`` raises it ``from`` the driver's
    IntegrityError, so the cause is what carries the constraint name that tells
    a missing agent apart from a missing organization.
    """
    cfg = opts or LedgerFkViolationOpts()
    error = LedgerValidationError("idempotency ledger claim references unknown rows")
    error.__cause__ = _integrity_error(
        message=cfg.message,
        sqlstate=cfg.sqlstate,
        constraint_name=cfg.constraint_name,
    )
    return error
