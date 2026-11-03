"""Unresolved-conflict suppression across the hot + cold merge (5.B.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

import pytest

from app.assemble import AssembleRequest, ContextAssembler
from app.budget import Message, TokenBudget
from app.capability_catalog import TokenizerFamilyPolicy
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.conflict import collapse_conflicts
from app.estimate import ESTIMATE_CHARS_DIV_4
from app.packer import ContextPacker
from app.pipeline import pack_retrieval
from app.retrieval import (
    BranchOutcome,
    MemoryHit,
    ParallelRetriever,
    ResolvedDirective,
    RetrievalResult,
)

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"
POLICY = TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02)
GROUP = str(uuid4())


def _base_fields(
    content: str,
    *,
    similarity: float,
    groups: Sequence[str],
) -> dict[str, object]:
    """The shared shape of a retrieval hit and its HTTP payload fixture."""
    return {
        "memory_id": str(uuid4()),
        "org_id": str(ORG),
        "agent_id": str(AGENT),
        "content": content,
        "category": "factual",
        "confidence": 0.8,
        "similarity": similarity,
        "rank": 1,
        "conflict_groups": tuple(groups),
    }


def _hit(
    content: str,
    *,
    similarity: float = 0.8,
    groups: Sequence[str] = (),
    source: str = "vector",
) -> MemoryHit:
    return MemoryHit(
        **_base_fields(content, similarity=similarity, groups=groups),
        source=source,
    )


def _result(*, hot: list[MemoryHit] | None = None, cold: list[MemoryHit] | None = None) -> RetrievalResult:
    ok = BranchOutcome("success", 1.0)
    return RetrievalResult(
        directive=ResolvedDirective("Be careful.", "system_first", None),
        directive_outcome=ok,
        hot_memories=hot or [],
        hot_outcome=ok,
        cold_memories=cold or [],
        cold_outcome=ok,
        recent_messages=[],
        history_tokens=0,
        sources_available=frozenset({"directive", "hot", "cold"}),
    )


def _budget(usable: int = 4000) -> TokenBudget:
    return TokenBudget(
        context_window=128_000,
        response_reserve=4096,
        safety_buffer=2560,
        usable_budget=usable,
        directive_tokens=10,
        messages_tokens=20,
        is_constrained=False,
        estimate_kind=ESTIMATE_CHARS_DIV_4,
    )


def _packer() -> ContextPacker:
    return ContextPacker(POLICY)


def test_collapse_keeps_the_higher_interim_score() -> None:
    high = _hit("winner", similarity=0.95, groups=[GROUP])
    low = _hit("loser", similarity=0.10, groups=[GROUP])

    assert collapse_conflicts([low, high]) == [high]


def test_collapse_breaks_score_ties_on_memory_id() -> None:
    first = replace(
        _hit("a", groups=[GROUP]),
        memory_id="11111111-1111-1111-1111-111111111111",
    )
    second = replace(
        _hit("b", groups=[GROUP]),
        memory_id="22222222-2222-2222-2222-222222222222",
    )

    kept = collapse_conflicts([second, first])

    assert kept == [first]


def test_collapse_keeps_disjoint_and_ungrouped_hits() -> None:
    one = _hit("one", groups=[str(uuid4())])
    two = _hit("two", groups=[str(uuid4())])
    three = _hit("three")

    kept = collapse_conflicts([one, two, three])

    assert {hit.content for hit in kept} == {"one", "two", "three"}


def test_collapse_surviving_set_has_no_conflicting_pair() -> None:
    other = str(uuid4())
    a = _hit("a", similarity=0.9, groups=[GROUP])
    b = _hit("b", similarity=0.8, groups=[GROUP, other])
    c = _hit("c", similarity=0.7, groups=[other])

    kept = collapse_conflicts([a, b, c])

    groups = [group for hit in kept for group in hit.conflict_groups]
    assert len(groups) == len(set(groups))


def test_pack_retrieval_drops_the_losing_side() -> None:
    high = _hit("winner", similarity=0.95, groups=[GROUP])
    low = _hit("loser", similarity=0.10, groups=[GROUP])

    packed = pack_retrieval(
        _result(hot=[low], cold=[high]), _budget(), packer=_packer()
    )

    assert [memory.content for memory in packed.memories] == ["winner"]


def test_conflict_is_collapsed_across_hot_and_cold() -> None:
    hot_side = _hit("hot side", similarity=0.90, groups=[GROUP], source="hot_cache")
    cold_side = _hit("cold side", similarity=0.20, groups=[GROUP])

    packed = pack_retrieval(
        _result(hot=[hot_side], cold=[cold_side]), _budget(), packer=_packer()
    )

    assert [memory.content for memory in packed.memories] == ["hot side"]


class _StubMemory:
    def __init__(self, hot: list[MemoryHitPayload], cold: list[MemoryHitPayload]) -> None:
        self._hot = hot
        self._cold = cold

    async def get_hot_memories(self, *_args, **_kwargs):
        return self._hot

    async def search_memories(self, *_args, **_kwargs):
        return self._cold


class _StubDirective:
    async def lookup(self, _org_id, _agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Be careful.", injection_mode="system_first", version_id=None
        )


def _payload(content: str, *, similarity: float, groups: Sequence[str]) -> MemoryHitPayload:
    return MemoryHitPayload(
        **_base_fields(content, similarity=similarity, groups=groups),
        source="vector",
    )


def _assembler(memory: _StubMemory) -> ContextAssembler:
    settings = ContextSettings.model_construct(
        timeout_ms=45.0,
        deadline_ms=40.0,
        directive_timeout_ms=5.0,
        hot_timeout_ms=15.0,
        cold_timeout_ms=45.0,
        formatter_nonce_bytes=16,
        packer_dp_cell_ceiling=70 * 6251,
        packer_max_consecutive_skips=5,
    )
    return ContextAssembler(
        settings=settings,
        retriever=ParallelRetriever(
            settings=settings,
            memory=memory,  # type: ignore[arg-type]
            directive=_StubDirective(),
        ),
    )


@pytest.mark.asyncio
async def test_assembled_context_never_contains_both_sides_of_a_conflict() -> None:
    # Golden-output shape: the losing side must be absent from the formatted
    # context, not merely ranked lower.
    memory = _StubMemory(
        hot=[_payload("the sky is green", similarity=0.20, groups=[GROUP])],
        cold=[_payload("the sky is blue", similarity=0.95, groups=[GROUP])],
    )
    request = AssembleRequest(
        org_id=ORG,
        agent_id=AGENT,
        query="sky colour",
        model=MODEL,
        recent_messages=[Message(role="user", content="hello")],
    )

    result = await _assembler(memory).assemble(request)

    assert result.degradation_level == "L0"
    assert "the sky is blue" in result.formatted.assembled_context
    assert "the sky is green" not in result.formatted.assembled_context
    assert result.formatted.memories_included == 1


@pytest.mark.asyncio
async def test_unconflicted_memories_are_still_packed_together() -> None:
    memory = _StubMemory(
        hot=[_payload("hot fact", similarity=0.9, groups=[])],
        cold=[_payload("cold fact", similarity=0.85, groups=[str(uuid4())])],
    )
    request = AssembleRequest(
        org_id=ORG,
        agent_id=AGENT,
        query="theme",
        model=MODEL,
        recent_messages=[Message(role="user", content="hello")],
    )

    result = await _assembler(memory).assemble(request)

    assert result.formatted.memories_included == 2


def test_collapse_is_order_independent_for_disjoint_groups() -> None:
    # Output order comes from the sort, not from branch completion order.
    first = _hit("first", groups=[str(uuid4())])
    second = _hit("second", groups=[str(uuid4())])

    assert collapse_conflicts([first, second]) == collapse_conflicts([second, first])
