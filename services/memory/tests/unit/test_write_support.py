"""Unit tests for write cache, after-commit, persist helpers, and errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.conflict.types import ConflictDecision, ConflictOutcome
from app.write.after_commit import AfterCommitHandler
from app.write.cache import MemoryCacheWriter
from app.write.embed_context import get_write_org_id, reset_write_org_id, set_write_org_id
from app.write.errors import is_active_content_hash_violation
from app.write.models import WriteOutcome, WriteOutcomeKind
from app.write.persist import (
    content_token_count,
    escalations_from_decisions,
)
from tests.unit.memory_test_support import sample_memory_row


def _row():
    return sample_memory_row(content="hello world", content_tokens=2)


def test_content_token_count_minimum_one() -> None:
    assert content_token_count("one") == 1
    assert content_token_count("a b c") == 3


def test_escalations_from_decisions_filters() -> None:
    cid = uuid4()
    org = uuid4()
    new_id = uuid4()
    decisions = [
        ConflictDecision(
            candidate_id=cid,
            outcome=ConflictOutcome.ESCALATE_PENDING,
            llm_call_made=False,
            subject_key="k",
            notes="n",
        ),
        ConflictDecision(
            candidate_id=uuid4(),
            outcome=ConflictOutcome.NO_CONFLICT,
            llm_call_made=False,
            subject_key="k2",
        ),
    ]
    rows = escalations_from_decisions(org, new_id, decisions)
    assert len(rows) == 1
    assert rows[0].candidate_memory_id == cid


def test_embed_context_roundtrip() -> None:
    org = uuid4()
    token = set_write_org_id(org)
    try:
        assert get_write_org_id() == org
    finally:
        reset_write_org_id(token)


def test_is_active_content_hash_violation_diag_path() -> None:
    exc = IntegrityError("stmt", {}, Exception("dup"))
    orig = MagicMock()
    orig.sqlstate = "23505"
    orig.constraint_name = ""
    orig.diag = MagicMock(constraint_name="idx_memories_org_agent_content_hash_active")
    exc.orig = orig
    assert is_active_content_hash_violation(exc) is True


@pytest.mark.asyncio
async def test_cache_writer_skips_non_created() -> None:
    redis = AsyncMock()
    writer = MemoryCacheWriter(redis, Settings())
    await writer.write_created(
        WriteOutcome(kind=WriteOutcomeKind.QUARANTINED, memory=_row())
    )
    redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_cache_writer_object_cache_success() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    writer = MemoryCacheWriter(redis, Settings())
    outcome = WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_row())
    await writer.write_created(outcome)
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_writer_redis_error_fail_open() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(side_effect=RedisError("down"))
    redis.zadd = AsyncMock(side_effect=RedisError("down"))
    writer = MemoryCacheWriter(redis, Settings())
    await writer.write_created(
        WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=_row())
    )


@pytest.mark.asyncio
async def test_after_commit_vector_upsert() -> None:
    store = AsyncMock()
    store.upsert = AsyncMock()
    handler = AfterCommitHandler(cache=None, store=store)
    row = _row()
    await handler(
        WriteOutcome(
            kind=WriteOutcomeKind.CREATED,
            memory=row,
            embedding=(0.0,) * 1024,
            embedding_model="bge-m3",
        )
    )
    store.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_after_commit_vector_failure_fail_open() -> None:
    store = AsyncMock()
    store.upsert = AsyncMock(side_effect=LookupError("missing"))
    handler = AfterCommitHandler(cache=None, store=store)
    await handler(
        WriteOutcome(
            kind=WriteOutcomeKind.CREATED,
            memory=_row(),
            embedding=(0.0,) * 1024,
        )
    )
