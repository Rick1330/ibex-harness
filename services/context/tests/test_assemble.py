"""Unit tests for ContextAssembler degradation ladder (milestone 3.5.C.6)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.assemble import (
    AssembleRequest,
    AssemblyOptions,
    ContextAssembler,
)
from app.budget import Message
from app.clients.directive import DirectiveLookupError, DirectivePayload
from app.clients.memory import MemoryHitPayload, MemoryHttpError, MemoryHttpTimeout
from app.config import ContextSettings
from app.retrieval import ParallelRetriever

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"


def _settings(**overrides: object) -> ContextSettings:
    base: dict[str, object] = {
        "timeout_ms": 45.0,
        "deadline_ms": 40.0,
        "directive_timeout_ms": 5.0,
        "hot_timeout_ms": 15.0,
        "cold_timeout_ms": 45.0,
        "formatter_nonce_bytes": 16,
        "packer_dp_cell_ceiling": 70 * 6251,
        "packer_max_consecutive_skips": 5,
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


def _hit(*, source: str = "hot_cache", content: str = "prefers dark mode") -> MemoryHitPayload:
    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(ORG),
        agent_id=str(AGENT),
        content=content,
        category="preference",
        confidence=0.9,
        similarity=0.8,
        rank=1,
        source=source,
    )


class _StubDirective:
    def __init__(self, payload: DirectivePayload | Exception, delay_s: float = 0.0) -> None:
        self._payload = payload
        self._delay_s = delay_s

    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubMemory:
    def __init__(
        self,
        *,
        hot: list[MemoryHitPayload] | Exception | None = None,
        cold: list[MemoryHitPayload] | Exception | None = None,
        hot_delay_s: float = 0.0,
        cold_delay_s: float = 0.0,
    ) -> None:
        self._hot = [] if hot is None else hot
        self._cold = [] if cold is None else cold
        self._hot_delay_s = hot_delay_s
        self._cold_delay_s = cold_delay_s

    async def get_hot_memories(self, *_args, **_kwargs):
        if self._hot_delay_s:
            await asyncio.sleep(self._hot_delay_s)
        if isinstance(self._hot, Exception):
            raise self._hot
        return self._hot

    async def search_memories(self, *_args, **_kwargs):
        if self._cold_delay_s:
            await asyncio.sleep(self._cold_delay_s)
        if isinstance(self._cold, Exception):
            raise self._cold
        return self._cold


def _assembler(
    *,
    directive: _StubDirective | None = None,
    memory: _StubMemory | None = None,
    settings: ContextSettings | None = None,
) -> ContextAssembler:
    cfg = settings or _settings()
    retriever = ParallelRetriever(
        settings=cfg,
        memory=memory
        or _StubMemory(  # type: ignore[arg-type]
            hot=[_hit()],
            cold=[_hit(source="vector", content="cold fact")],
        ),
        directive=directive
        or _StubDirective(
            DirectivePayload(
                content="Be careful.",
                injection_mode="system_first",
                version_id=None,
            )
        ),
    )
    return ContextAssembler(settings=cfg, retriever=retriever)


def _req(**kwargs: object) -> AssembleRequest:
    base: dict[str, object] = {
        "org_id": ORG,
        "agent_id": AGENT,
        "query": "theme",
        "model": MODEL,
        "recent_messages": [Message(role="user", content="hello")],
    }
    base.update(kwargs)
    return AssembleRequest(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_assemble_l0_full() -> None:
    hot = _hit(content="hot preference")
    cold = _hit(source="vector", content="cold fact")
    result = await _assembler(memory=_StubMemory(hot=[hot], cold=[cold])).assemble(_req())
    assert result.degradation_level == "L0"
    assert result.formatted.memories_included >= 1
    assert "Be careful." in result.formatted.assembled_context
    assert result.metrics.candidates_evaluated >= 1
    assert result.metrics.total_ms >= 0
    assert result.metrics.ranking_ms >= 0
    assert result.metrics.packing_ms >= 0
    assert result.metrics.formatting_ms >= 0
    assert result.packed.path in ("dp", "greedy")


@pytest.mark.asyncio
async def test_assemble_l1_cold_timeout() -> None:
    hot = _hit(content="hot only")
    memory = _StubMemory(hot=[hot], cold_delay_s=0.2)
    settings = _settings(cold_timeout_ms=20.0, timeout_ms=100.0, deadline_ms=100.0)
    result = await _assembler(memory=memory, settings=settings).assemble(_req())
    assert result.degradation_level == "L1"
    assert result.retrieval.cold_outcome.status == "timeout"
    assert result.retrieval.hot_outcome.status == "success"
    assert result.formatted.memories_included >= 1
    assert result.metrics.candidates_evaluated == result.packed.candidates_evaluated


@pytest.mark.asyncio
async def test_assemble_l2_both_memory_fail() -> None:
    memory = _StubMemory(
        hot=MemoryHttpError("hot down"),
        cold=MemoryHttpTimeout("cold timeout"),
    )
    result = await _assembler(memory=memory).assemble(_req())
    assert result.degradation_level == "L2"
    assert result.formatted.memories_included == 0
    assert result.packed.memories == ()
    assert "Be careful." in result.formatted.assembled_context
    assert result.metrics.candidates_evaluated == 0


@pytest.mark.asyncio
async def test_assemble_skip_cold_intentional_l1() -> None:
    hot = _hit(content="hot only")
    cold = _hit(source="vector", content="should be skipped")
    result = await _assembler(memory=_StubMemory(hot=[hot], cold=[cold])).assemble(
        _req(options=AssemblyOptions(skip_cold_memories=True))
    )
    assert result.degradation_level == "L1"
    assert all(m.content != "should be skipped" for m in result.packed.memories)
    assert result.formatted.memories_included >= 1


@pytest.mark.asyncio
async def test_assemble_skip_hot_and_cold_intentional_l2() -> None:
    hot = _hit(content="hot skipped")
    cold = _hit(source="vector", content="cold skipped")
    result = await _assembler(memory=_StubMemory(hot=[hot], cold=[cold])).assemble(
        _req(
            options=AssemblyOptions(
                skip_hot_memories=True,
                skip_cold_memories=True,
            )
        )
    )
    assert result.degradation_level == "L2"
    assert result.formatted.memories_included == 0


@pytest.mark.asyncio
async def test_assemble_max_memories_caps_scored() -> None:
    hot = MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(ORG),
        agent_id=str(AGENT),
        content="hot-a",
        category="preference",
        confidence=0.95,
        similarity=0.9,
        rank=1,
        source="hot_cache",
    )
    cold = MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(ORG),
        agent_id=str(AGENT),
        content="cold-b",
        category="preference",
        confidence=0.8,
        similarity=0.7,
        rank=2,
        source="vector",
    )
    result = await _assembler(
        memory=_StubMemory(hot=[hot], cold=[cold]),
    ).assemble(_req(options=AssemblyOptions(max_memories=1)))
    assert result.degradation_level == "L0"
    assert len(result.packed.memories) <= 1
    assert result.metrics.candidates_evaluated <= 1


@pytest.mark.asyncio
async def test_assemble_deterministic_repeat() -> None:
    hot = _hit(content="same hot")
    cold = _hit(source="vector", content="same cold")
    memory = _StubMemory(hot=[hot], cold=[cold])
    a = _assembler(memory=memory)
    first = await a.assemble(_req())
    # Same stub payloads — second call needs fresh stub (memory already returned lists).
    second = await _assembler(
        memory=_StubMemory(hot=[hot], cold=[cold]),
    ).assemble(_req())
    assert first.packed.path == second.packed.path
    assert first.degradation_level == second.degradation_level == "L0"
    # Nonce differs per assembly; section structure should match aside from nonce.
    assert first.formatted.memories_included == second.formatted.memories_included


@pytest.mark.asyncio
async def test_assemble_metrics_non_negative_l0() -> None:
    result = await _assembler().assemble(_req())
    m = result.metrics
    for value in (
        m.budget_calculation_ms,
        m.directive_load_ms,
        m.hot_memory_retrieval_ms,
        m.cold_memory_retrieval_ms,
        m.ranking_ms,
        m.packing_ms,
        m.formatting_ms,
        m.total_ms,
        m.candidates_evaluated,
    ):
        assert value >= 0
    assert m.total_ms >= max(m.ranking_ms, m.packing_ms, m.formatting_ms)


@pytest.mark.asyncio
async def test_assemble_directive_error_still_packs_memories() -> None:
    result = await _assembler(
        directive=_StubDirective(DirectiveLookupError("redis down")),
    ).assemble(_req())
    assert result.degradation_level == "L0"
    assert result.retrieval.directive is None
    assert result.formatted.memories_included >= 1


@pytest.mark.asyncio
async def test_retrieval_wall_uses_deadline_ms() -> None:
    settings = _settings(timeout_ms=45.0, deadline_ms=40.0)
    assert settings.retrieval_wall_ms == 40.0
    settings2 = _settings(timeout_ms=30.0, deadline_ms=40.0)
    assert settings2.retrieval_wall_ms == 30.0
