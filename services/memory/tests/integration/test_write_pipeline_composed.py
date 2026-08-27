"""Composed WritePipeline stages 1–6 against Postgres (Track C closeout)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.persist import CandidateLoad, load_candidate_memories
from app.conflict.service import ConflictService
from app.dedup.hash import content_hash_sha256
from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)
from app.dedup.service import DedupService
from app.pii.service import PiiService
from app.pii.types import PiiFinding, PiiProcessResult
from app.pipeline import (
    ConflictStage,
    EmbedStage,
    ExactDedupStage,
    NearDedupStage,
    PiiStage,
    ValidateStage,
    WriteContext,
    WritePipeline,
)
from app.vectorstore.base import UpsertRequest
from app.vectorstore.pgvector_store import PgVectorStore
from tests.integration.conftest import seed_org_agent_memory, zero_embedding

pytestmark = pytest.mark.integration


class _EmbedProbe:
    """Records texts passed to embed (ordering invariant)."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def __call__(self, payload: str) -> list[float]:
        self.seen.append(payload)
        return zero_embedding(hotspot=3)


class _QuarantinePii:
    """Deterministic quarantine without relying on Presidio score variance."""

    async def process_async(self, content: str) -> PiiProcessResult:
        return PiiProcessResult(
            findings=[PiiFinding("PERSON", 0, min(6, len(content)), 0.40)],
            content=content,
            pii_detected=True,
            pii_redacted=False,
            status="quarantined",
            quarantine_reason="pii_low_confidence",
        )


async def _set_content_hash(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    content_hash: str,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.current_org_id', :org_id, true)"
            ),
            {"org_id": str(org_id)},
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                UPDATE ibex_core.memories
                SET content_hash = :hash
                WHERE id = :id AND org_id = :org_id
                """
            ),
            {"hash": content_hash, "id": str(memory_id), "org_id": str(org_id)},
        )


def _build_pipeline(deps: SimpleNamespace) -> WritePipeline:
    """Assemble validate → pii → exact → embed → near → conflict."""

    async def load(org_id: UUID, ids: Sequence[UUID]) -> list:
        return await load_candidate_memories(
            deps.factory, CandidateLoad(org_id=org_id, memory_ids=tuple(ids))
        )

    return WritePipeline(
        [
            ValidateStage(deps.settings),
            PiiStage(deps.pii),
            ExactDedupStage(deps.dedup),
            EmbedStage(deps.embed),
            NearDedupStage(deps.dedup),
            ConflictStage(deps.conflict, load_candidates=load, enabled=True),
        ]
    )


def _make_deps(core: SimpleNamespace) -> SimpleNamespace:
    """core fields: factory, settings, store; optional pii, embed."""
    factory = core.factory
    settings = core.settings
    store = core.store

    async def lookup(o: UUID, a: UUID, h: str) -> UUID | None:
        return await find_active_by_content_hash(
            factory, ExactHashLookup(org_id=o, agent_id=a, content_hash=h)
        )

    async def bump(o: UUID, mid: UUID) -> int:
        return await increment_retrieval_count(
            factory, RetrievalBump(org_id=o, memory_id=mid)
        )

    dedup = DedupService(
        settings, store=store, exact_lookup=lookup, bump_retrieval=bump
    )
    conflict = ConflictService(
        settings, subject_extractor=lambda _: "shared-subject-key"
    )
    probe = getattr(core, "embed", None) or _EmbedProbe()
    pii = getattr(core, "pii", None) or PiiService(settings)
    return SimpleNamespace(
        factory=factory,
        settings=settings,
        dedup=dedup,
        conflict=conflict,
        pii=pii,
        embed=probe,
    )


def _core(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> SimpleNamespace:
    return SimpleNamespace(factory=factory, settings=settings, store=store)


@pytest.mark.asyncio
async def test_composed_happy_path_novel_clean(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="seed unrelated row"
    )
    content = "User prefers dark mode in dashboards for focus"
    core = _core(session_factory, settings, store)
    deps = _make_deps(core)
    if hasattr(deps.pii, "ensure_ready"):
        await deps.pii.ensure_ready()
    pipe = _build_pipeline(deps)
    ctx = await pipe.run(
        WriteContext(
            org_id=org_id,
            agent_id=agent_id,
            content=content,
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    assert ctx.stop is False
    assert ctx.error is None
    assert ctx.status != "quarantined"
    assert ctx.embedding is not None
    assert ctx.near_duplicate_candidates == []
    assert ctx.conflict_decisions == []
    assert ctx.pending_supersede_targets == []
    assert deps.embed.seen == [ctx.content]
    assert ctx.content_hash == content_hash_sha256(ctx.content)


@pytest.mark.asyncio
async def test_composed_pii_quarantine_stops_before_embed(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="quarantine seed"
    )
    probe = _EmbedProbe()
    core = _core(session_factory, settings, store)
    core.pii = _QuarantinePii()
    core.embed = probe
    deps = _make_deps(core)
    pipe = _build_pipeline(deps)
    ctx = await pipe.run(
        WriteContext(org_id=org_id, agent_id=agent_id, content="Contact Jordan")
    )
    assert ctx.stop is True
    assert ctx.status == "quarantined"
    assert ctx.embedding is None
    assert probe.seen == []
    assert ctx.near_duplicate_candidates == []
    assert ctx.conflict_decisions == []


@pytest.mark.asyncio
async def test_composed_exact_duplicate_stops_before_embed(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    content = "Exact duplicate payload for composed pipeline"
    digest = content_hash_sha256(content)
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=content
    )
    await _set_content_hash(
        session_factory, org_id=org_id, memory_id=memory_id, content_hash=digest
    )
    probe = _EmbedProbe()
    core = _core(session_factory, settings, store)
    core.embed = probe
    deps = _make_deps(core)
    if hasattr(deps.pii, "ensure_ready"):
        await deps.pii.ensure_ready()
    pipe = _build_pipeline(deps)
    ctx = await pipe.run(
        WriteContext(org_id=org_id, agent_id=agent_id, content=content)
    )
    assert ctx.stop is True
    assert ctx.is_exact_duplicate is True
    assert ctx.existing_memory_id == memory_id
    assert ctx.embedding is None
    assert probe.seen == []
    assert ctx.near_duplicate_candidates == []
    assert ctx.conflict_decisions == []


@pytest.mark.asyncio
async def test_composed_missing_agent_id_stops_at_exact_dedup(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    org_id, _, _ = await seed_org_agent_memory(
        session_factory, content="agent id gate seed"
    )
    probe = _EmbedProbe()
    core = _core(session_factory, settings, store)
    core.embed = probe
    deps = _make_deps(core)
    if hasattr(deps.pii, "ensure_ready"):
        await deps.pii.ensure_ready()
    pipe = _build_pipeline(deps)
    ctx = await pipe.run(
        WriteContext(org_id=org_id, agent_id=None, content="novel clean preference text")
    )
    assert ctx.stop is True
    assert ctx.error == "agent_id_required"
    assert ctx.embedding is None
    assert probe.seen == []


@pytest.mark.asyncio
async def test_composed_cross_tenant_near_dup_isolation(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store: PgVectorStore,
) -> None:
    content_a = "Shared preference wording for tenant A"
    content_b = "Shared preference wording for tenant B"
    org_a, agent_a, mem_a = await seed_org_agent_memory(
        session_factory, content=content_a
    )
    org_b, agent_b, mem_b = await seed_org_agent_memory(
        session_factory, content=content_b
    )
    vec = zero_embedding(hotspot=11)
    await store.upsert(
        UpsertRequest(
            memory_id=mem_a,
            org_id=org_a,
            embedding=vec,
            embedding_model="test-model",
        )
    )
    await store.upsert(
        UpsertRequest(
            memory_id=mem_b,
            org_id=org_b,
            embedding=vec,
            embedding_model="test-model",
        )
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    core = _core(session_factory, settings, store)
    core.embed = embed
    deps = _make_deps(core)
    if hasattr(deps.pii, "ensure_ready"):
        await deps.pii.ensure_ready()
    pipe = _build_pipeline(deps)

    ctx_a = await pipe.run(
        WriteContext(
            org_id=org_a,
            agent_id=agent_a,
            content="another write for org A similar vector",
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    assert mem_a in ctx_a.near_duplicate_candidates
    assert mem_b not in ctx_a.near_duplicate_candidates

    ctx_b = await pipe.run(
        WriteContext(
            org_id=org_b,
            agent_id=agent_b,
            content="another write for org B similar vector",
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    assert mem_b in ctx_b.near_duplicate_candidates
    assert mem_a not in ctx_b.near_duplicate_candidates

    # Org B must not bump org A retrieval via exact path with shared wording.
    digest = content_hash_sha256(content_a)
    await _set_content_hash(
        session_factory, org_id=org_a, memory_id=mem_a, content_hash=digest
    )
    found = await find_active_by_content_hash(
        session_factory,
        ExactHashLookup(org_id=org_b, agent_id=agent_b, content_hash=digest),
    )
    assert found is None
