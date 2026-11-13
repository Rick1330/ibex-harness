"""The configured embedding identity reaches storage instead of a literal (W10.3).

Two writers name the generation on a stored vector: ``WriteOutcome.embedding_model``
from the orchestrator and the ``AfterCommitHandler`` fallback used for an outcome that
carries an embedding but no id. They must resolve to the same configured identity
(``id`` or ``id@revision``), otherwise the row and its vector index entry can disagree
about which generation produced the numbers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from app.pipeline.context import WriteContext
from app.write.after_commit import AfterCommitHandler
from app.write.models import CreateMemoryCommand, WriteOutcome, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator
from tests.unit.memory_test_support import mock_async_session_factory, sample_memory_row

_EMBEDDING = [0.5] * 1024


class _EmbeddingPipe:
    """Minimal pipeline: an active write that already embedded its content."""

    def __init__(self, embedding: list[float] | None = _EMBEDDING) -> None:
        self._embedding = embedding

    async def run(self, ctx: WriteContext) -> WriteContext:
        ctx.status = "active"
        ctx.content_hash = "hash-1"
        ctx.embedding = self._embedding
        return ctx


async def _create(
    *,
    embedding_model: str | None = None,
    after_commit=None,
    pipe: _EmbeddingPipe | None = None,
):
    orchestrator = MemoryWriteOrchestrator(
        pipe or _EmbeddingPipe(),
        mock_async_session_factory(),
        after_commit=after_commit,
        embedding_model=embedding_model,
    )
    row = sample_memory_row()
    with (
        patch("app.write.orchestrator.lock_organization_for_memory_write", AsyncMock()),
        patch("app.write.orchestrator.insert_memory_session", AsyncMock(return_value=row)),
        patch("app.write.orchestrator.insert_labels_session", AsyncMock(return_value=1)),
        patch("app.write.orchestrator.reload_memory_session", AsyncMock(return_value=row)),
        patch("app.write.orchestrator.enqueue_memory_lifecycle_event", AsyncMock()),
    ):
        return await orchestrator.create(
            CreateMemoryCommand(org_id=uuid4(), agent_id=uuid4(), content="x")
        )


@pytest.mark.asyncio
async def test_configured_model_id_is_stamped_on_the_outcome() -> None:
    outcome = await _create(embedding_model="custom-embed")
    assert outcome.embedding_model == "custom-embed"


@pytest.mark.asyncio
async def test_default_model_id_matches_the_previous_literal() -> None:
    outcome = await _create()
    assert outcome.embedding_model == "bge-m3"


@pytest.mark.asyncio
async def test_orchestrator_reads_the_process_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.config.get_settings", lambda: Settings(embedding_model="env-configured")
    )
    outcome = await _create()
    assert outcome.embedding_model == "env-configured"


@pytest.mark.asyncio
async def test_no_embedding_leaves_the_model_unset() -> None:
    outcome = await _create(pipe=_EmbeddingPipe(embedding=None))
    assert outcome.embedding_model is None


@pytest.mark.asyncio
async def test_configured_model_id_reaches_the_vector_upsert() -> None:
    """The end-to-end claim: config → outcome → UpsertRequest.embedding_model."""
    store = MagicMock()
    store.upsert = AsyncMock()
    handler = AfterCommitHandler(cache=None, store=store)

    outcome = await _create(embedding_model="custom-embed", after_commit=handler)

    store.upsert.assert_awaited_once()
    request = store.upsert.await_args.args[0]
    assert request.embedding_model == "custom-embed"
    assert request.memory_id == outcome.memory.id


@pytest.mark.asyncio
async def test_after_commit_falls_back_to_the_configured_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.config.get_settings", lambda: Settings(embedding_model="handler-default")
    )
    store = MagicMock()
    store.upsert = AsyncMock()
    handler = AfterCommitHandler(cache=None, store=store)

    await handler(
        WriteOutcome(
            kind=WriteOutcomeKind.CREATED,
            memory=sample_memory_row(),
            embedding=tuple(_EMBEDDING),
        )
    )

    request = store.upsert.await_args.args[0]
    assert request.embedding_model == "handler-default"


@pytest.mark.asyncio
async def test_after_commit_prefers_the_outcome_identity() -> None:
    store = MagicMock()
    store.upsert = AsyncMock()
    handler = AfterCommitHandler(cache=None, store=store, embedding_model="fallback")

    await handler(
        WriteOutcome(
            kind=WriteOutcomeKind.CREATED,
            memory=sample_memory_row(),
            embedding=tuple(_EMBEDDING),
            embedding_model="from-outcome",
        )
    )

    request = store.upsert.await_args.args[0]
    assert request.embedding_model == "from-outcome"


@pytest.mark.asyncio
async def test_configured_revision_reaches_the_outcome_and_the_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One composite identity, not an id from one writer and a revision from the other."""
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: Settings(embedding_model="bge-m3", embedding_model_revision="r1"),
    )
    store = MagicMock()
    store.upsert = AsyncMock()
    handler = AfterCommitHandler(cache=None, store=store)

    outcome = await _create(after_commit=handler)

    assert outcome.embedding_model == "bge-m3@r1"
    request = store.upsert.await_args.args[0]
    assert request.embedding_model == outcome.embedding_model
