"""Pipeline ordering: exact before embed; near after embed; exact skip embed."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.dedup.hash import content_hash_sha256
from app.dedup.service import DedupService
from app.pii.service import PiiService
from app.pipeline import (
    EmbedStage,
    ExactDedupStage,
    NearDedupStage,
    PiiStage,
    ValidateStage,
    WriteContext,
    WritePipeline,
)
from app.vectorstore.base import UpsertRequest
from app.vectorstore.memory import InMemoryVectorStore


def test_write_pipeline_stage_names() -> None:
    settings = Settings()

    async def embed(text: str) -> list[float]:
        del text
        return [0.0]

    pipe = WritePipeline([ValidateStage(settings), EmbedStage(embed)])
    assert pipe.stage_names == ["validate", "embed"]


@pytest.mark.asyncio
async def test_near_stage_records_novel_when_no_candidates() -> None:
    settings = Settings(near_duplicate_sim_threshold=0.92)
    store = InMemoryVectorStore()

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        return None

    async def embed(_text: str) -> list[float]:
        return [0.0] * 1023 + [1.0]

    dedup = DedupService(settings, store=store, exact_lookup=lookup)
    pipe = WritePipeline(
        [
            ExactDedupStage(dedup),
            EmbedStage(embed),
            NearDedupStage(dedup),
        ]
    )
    ctx = await pipe.run(
        WriteContext(org_id=uuid4(), agent_id=uuid4(), content="lonely novel memory")
    )
    assert ctx.near_duplicate_candidates == []
    assert ctx.is_exact_duplicate is False

    settings = Settings(max_content_chars=8)
    pipe = WritePipeline([ValidateStage(settings)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content="0123456789"))
    assert ctx.stop is True
    assert ctx.error == "content_too_long"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage_factory", "ctx_kwargs", "want_error"),
    [
        (
            lambda settings, lookup: ExactDedupStage(
                DedupService(settings, exact_lookup=lookup)
            ),
            {"content": "x"},
            "agent_id_required",
        ),
        (
            lambda settings, lookup: NearDedupStage(
                DedupService(settings, exact_lookup=lookup, store=InMemoryVectorStore())
            ),
            {"agent_id": uuid4(), "content": "x", "embedding": None},
            "embedding_required",
        ),
        (
            lambda settings, lookup: NearDedupStage(
                DedupService(settings, exact_lookup=lookup, store=InMemoryVectorStore())
            ),
            {"content": "x", "embedding": [0.0] * 1024},
            "agent_id_required",
        ),
    ],
)
async def test_dedup_stages_require_context(
    stage_factory: object,
    ctx_kwargs: dict,
    want_error: str,
) -> None:
    settings = Settings()

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        return None

    pipe = WritePipeline([stage_factory(settings, lookup)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), **ctx_kwargs))
    assert ctx.stop is True
    assert ctx.error == want_error

    settings = Settings()
    pipe = WritePipeline([ValidateStage(settings)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content="   "))
    assert ctx.stop is True
    assert ctx.error == "content_empty"


@pytest.mark.asyncio
async def test_exact_duplicate_skips_embed_and_near() -> None:
    settings = Settings()
    existing = uuid4()
    org, agent = uuid4(), uuid4()
    content = "User prefers typed placeholders"

    async def lookup(o: UUID, a: UUID, h: str) -> UUID | None:
        assert o == org and a == agent
        assert h == content_hash_sha256(content)
        return existing

    async def bump(o: UUID, mid: UUID) -> int:
        assert o == org and mid == existing
        return 2

    seen: list[str] = []

    async def embed(text: str) -> list[float]:
        seen.append(text)
        return [0.0] * 1024

    dedup = DedupService(settings, exact_lookup=lookup, bump_retrieval=bump)
    pipe = WritePipeline(
        [
            ValidateStage(settings),
            ExactDedupStage(dedup),
            EmbedStage(embed),
            NearDedupStage(dedup),
        ]
    )
    ctx = await pipe.run(WriteContext(org_id=org, agent_id=agent, content=content))
    assert ctx.is_exact_duplicate is True
    assert ctx.existing_memory_id == existing
    assert ctx.stop is True
    assert seen == []
    assert ctx.near_duplicate_candidates == []
    assert ctx.embedding is None


@pytest.mark.asyncio
async def test_novel_runs_embed_then_near_dup() -> None:
    settings = Settings(near_duplicate_sim_threshold=0.92)
    store = InMemoryVectorStore()
    org, agent = uuid4(), uuid4()
    near_id = uuid4()
    store.bind_agent(near_id, agent)
    vec = [0.0] * 1023 + [1.0]
    await store.upsert(
        UpsertRequest(
            memory_id=near_id, org_id=org, embedding=vec, embedding_model="test"
        )
    )

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        return None

    stage_order: list[str] = []

    async def embed(text: str) -> list[float]:
        del text
        stage_order.append("embed")
        return list(vec)

    dedup = DedupService(settings, store=store, exact_lookup=lookup)
    near = NearDedupStage(dedup)

    class _OrderNear(NearDedupStage):
        async def process(self, ctx: WriteContext) -> WriteContext:
            stage_order.append("near")
            return await near.process(ctx)

    pipe = WritePipeline(
        [
            ValidateStage(settings),
            ExactDedupStage(dedup),
            EmbedStage(embed),
            _OrderNear(dedup),
        ]
    )
    ctx = await pipe.run(
        WriteContext(org_id=org, agent_id=agent, content="brand new fact")
    )
    assert ctx.is_exact_duplicate is False
    assert stage_order == ["embed", "near"]
    assert near_id in ctx.near_duplicate_candidates


@pytest.mark.asyncio
async def test_embed_receives_only_redacted_content() -> None:
    settings = Settings(pii_redact_min_confidence=0.70)
    pii = PiiService(settings)
    seen: list[str] = []

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        return None

    async def embed(text: str) -> list[float]:
        seen.append(text)
        return [0.0] * 8

    dedup = DedupService(settings, exact_lookup=lookup)
    pipe = WritePipeline(
        [
            ValidateStage(settings),
            PiiStage(pii),
            ExactDedupStage(dedup),
            EmbedStage(embed),
        ]
    )
    raw = "Please email alice@example.com about the contract"
    ctx = await pipe.run(WriteContext(org_id=uuid4(), agent_id=uuid4(), content=raw))
    assert ctx.pii_detected is True
    if ctx.status == "quarantined":
        assert seen == []
        assert ctx.embedding is None
    else:
        assert ctx.pii_redacted is True
        assert len(seen) == 1
        assert "alice@example.com" not in seen[0]
        assert ctx.embedding is not None
        assert ctx.content_hash == content_hash_sha256(seen[0])


@pytest.mark.asyncio
async def test_quarantine_skips_exact_and_embed() -> None:
    settings = Settings(pii_redact_min_confidence=0.99)

    @dataclass
    class _FakeRecognizerResult:
        entity_type: str
        start: int
        end: int
        score: float

    class _FakeAnalyzer:
        def __init__(self, results: list[_FakeRecognizerResult]) -> None:
            self._results = results

        def analyze(
            self, text: str, language: str = "en", **_: object
        ) -> list[_FakeRecognizerResult]:
            del text, language
            return list(self._results)

    class _FakeAnonymizer:
        def anonymize(
            self, text: str, analyzer_results: list[object], operators: dict[str, object]
        ) -> object:
            del analyzer_results, operators

            class _R:
                def __init__(self, value: str) -> None:
                    self.text = value

            return _R(text)

    text = "Contact Jordan for details"
    start = text.index("Jordan")
    pii = PiiService(
        settings,
        analyzer=_FakeAnalyzer(  # type: ignore[arg-type]
            [_FakeRecognizerResult("PERSON", start, start + 6, 0.50)]
        ),
        anonymizer=_FakeAnonymizer(),  # type: ignore[arg-type]
    )
    seen: list[str] = []
    lookups = 0

    async def lookup(_o: UUID, _a: UUID, _h: str) -> UUID | None:
        nonlocal lookups
        lookups += 1
        return None

    async def embed(payload: str) -> list[float]:
        seen.append(payload)
        return [1.0]

    dedup = DedupService(settings, exact_lookup=lookup)
    pipe = WritePipeline(
        [
            ValidateStage(settings),
            PiiStage(pii),
            ExactDedupStage(dedup),
            EmbedStage(embed),
        ]
    )
    ctx = await pipe.run(WriteContext(org_id=uuid4(), agent_id=uuid4(), content=text))
    assert ctx.status == "quarantined"
    assert ctx.stop is True
    assert seen == []
    assert lookups == 0
    assert "Jordan" in ctx.content
