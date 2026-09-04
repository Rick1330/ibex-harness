"""Unit tests for ParallelRetriever failure modes (milestone 3.5.C.2)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.budget import Message
from app.clients.directive import DirectiveLookupError, DirectivePayload
from app.clients.memory import MemoryHitPayload, MemoryHttpError, MemoryHttpTimeout
from app.config import ContextSettings
from app.retrieval import ParallelRetriever, RetrievalRequest

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"


def _settings(**overrides: float) -> ContextSettings:
    base = {
        "timeout_ms": 45.0,
        "directive_timeout_ms": 5.0,
        "hot_timeout_ms": 15.0,
        "cold_timeout_ms": 45.0,
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


def _request(*, messages: list[Message] | None = None) -> RetrievalRequest:
    return RetrievalRequest(
        org_id=ORG,
        agent_id=AGENT,
        query="dark mode preference",
        model=MODEL,
        recent_messages=messages
        or [Message(role="user", content="I prefer dark mode")],
    )


def _hit(*, source: str = "hot_cache") -> MemoryHitPayload:
    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(ORG),
        agent_id=str(AGENT),
        content="prefers dark mode",
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
        self.hot_calls = 0
        self.cold_calls = 0

    async def get_hot_memories(self, *_args, **_kwargs):
        self.hot_calls += 1
        if self._hot_delay_s:
            await asyncio.sleep(self._hot_delay_s)
        if isinstance(self._hot, Exception):
            raise self._hot
        return self._hot

    async def search_memories(self, *_args, **_kwargs):
        self.cold_calls += 1
        if self._cold_delay_s:
            await asyncio.sleep(self._cold_delay_s)
        if isinstance(self._cold, Exception):
            raise self._cold
        return self._cold


def _retriever(
    *,
    directive: _StubDirective | None = None,
    memory: _StubMemory | None = None,
    settings: ContextSettings | None = None,
) -> ParallelRetriever:
    return ParallelRetriever(
        settings=settings or _settings(),
        memory=memory or _StubMemory(hot=[_hit()], cold=[_hit(source="vector")]),  # type: ignore[arg-type]
        directive=directive
        or _StubDirective(
            DirectivePayload(content="Be helpful.", injection_mode="system_first", version_id=None)
        ),
    )


@pytest.mark.asyncio
async def test_retrieve_all_succeed() -> None:
    result = await _retriever().retrieve(_request())
    assert result.sources_available == frozenset({"directive", "hot", "cold"})
    assert result.directive is not None
    assert result.directive.content == "Be helpful."
    assert len(result.hot_memories) == 1
    assert len(result.cold_memories) == 1
    assert result.history_tokens > 0
    assert result.directive_outcome.status == "success"
    assert result.hot_outcome.status == "success"
    assert result.cold_outcome.status == "success"


@pytest.mark.asyncio
async def test_retrieve_cold_times_out_keeps_hot_and_directive() -> None:
    memory = _StubMemory(hot=[_hit()], cold_delay_s=0.2)
    settings = _settings(cold_timeout_ms=20.0, timeout_ms=100.0)
    result = await _retriever(memory=memory, settings=settings).retrieve(_request())
    assert result.cold_outcome.status == "timeout"
    assert "cold" not in result.sources_available
    assert "hot" in result.sources_available
    assert "directive" in result.sources_available
    assert len(result.hot_memories) == 1


@pytest.mark.asyncio
async def test_retrieve_hot_times_out_keeps_others() -> None:
    memory = _StubMemory(hot_delay_s=0.2, cold=[_hit(source="vector")])
    settings = _settings(hot_timeout_ms=10.0, timeout_ms=100.0)
    result = await _retriever(memory=memory, settings=settings).retrieve(_request())
    assert result.hot_outcome.status == "timeout"
    assert "hot" not in result.sources_available
    assert "cold" in result.sources_available
    assert "directive" in result.sources_available


@pytest.mark.asyncio
async def test_retrieve_directive_fails_keeps_memories() -> None:
    directive = _StubDirective(DirectiveLookupError("boom"))
    result = await _retriever(directive=directive).retrieve(_request())
    assert result.directive_outcome.status == "error"
    assert result.directive is None
    assert "directive" not in result.sources_available
    assert "hot" in result.sources_available
    assert "cold" in result.sources_available


@pytest.mark.asyncio
async def test_retrieve_all_fail_non_crashing() -> None:
    memory = _StubMemory(
        hot=MemoryHttpError("hot down"),
        cold=MemoryHttpTimeout("cold timeout"),
    )
    directive = _StubDirective(DirectiveLookupError("redis down"))
    result = await _retriever(memory=memory, directive=directive).retrieve(_request())
    assert result.sources_available == frozenset()
    assert result.hot_memories == []
    assert result.cold_memories == []
    assert result.directive is None
    assert result.history_tokens > 0
    assert result.hot_outcome.status == "error"
    assert result.cold_outcome.status == "timeout"
    assert result.directive_outcome.status == "error"


@pytest.mark.asyncio
async def test_retrieve_empty_directive_is_success_without_payload() -> None:
    directive = _StubDirective(
        DirectivePayload(content="", injection_mode="system_first", version_id=None)
    )
    result = await _retriever(directive=directive).retrieve(_request())
    assert result.directive_outcome.status == "success"
    assert result.directive is None
    assert "directive" in result.sources_available


@pytest.mark.asyncio
async def test_retrieve_history_tokens_from_recent_messages() -> None:
    short = await _retriever().retrieve(
        _request(messages=[Message(role="user", content="hi")])
    )
    long = await _retriever().retrieve(
        _request(
            messages=[
                Message(role="user", content="x" * 400),
                Message(role="assistant", content="y" * 400),
            ]
        )
    )
    assert long.history_tokens > short.history_tokens


@pytest.mark.asyncio
async def test_retrieve_outer_deadline_keeps_finished_branches() -> None:
    """Slow cold cancelled by outer wait; fast directive+hot retained."""
    memory = _StubMemory(hot=[_hit()], cold_delay_s=0.5)
    settings = _settings(
        timeout_ms=30.0,
        directive_timeout_ms=20.0,
        hot_timeout_ms=20.0,
        cold_timeout_ms=500.0,
    )
    result = await _retriever(memory=memory, settings=settings).retrieve(_request())
    assert "directive" in result.sources_available
    assert "hot" in result.sources_available
    assert result.cold_outcome.status == "timeout"
    assert result.cold_outcome.detail == "outer_deadline"
