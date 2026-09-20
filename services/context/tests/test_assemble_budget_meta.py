"""Unit tests for assemble budget metadata helpers."""

from __future__ import annotations

from uuid import uuid4

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"


def _scored_memory(mid: str, content: str, score: float):
    from app.packer import ScoredMemory
    from app.retrieval import MemoryHit

    return ScoredMemory(
        hit=MemoryHit(
            memory_id=mid,
            org_id=str(ORG),
            agent_id=str(AGENT),
            content=content,
            category="factual",
            confidence=0.9,
            similarity=0.9,
            rank=1,
            source="vector",
        ),
        composite_score=score,
    )


def test_memories_used_marks_budget_exclusions() -> None:
    """Scored candidates not in packed.memories get exclusion=budget when fit failed."""
    from app.assemble import _memories_used
    from app.capability_catalog import default_catalog
    from app.packer import PackedMemories

    scored = [
        _scored_memory("a", "note", 1.0),
        _scored_memory("b", "note", 0.5),
        _scored_memory("c", "note", 0.2),
    ]
    packed = PackedMemories(
        memories=(scored[0],),
        total_tokens=10,
        total_score=1.0,
        skipped_count=2,
        was_budget_reached=True,
        path="dp",
        candidates_evaluated=3,
        budget_excluded_ids=frozenset({"b"}),
    )
    policy = default_catalog().family_policy(
        default_catalog().for_model(MODEL).tokenizer_family,
    )
    used = _memories_used(scored, packed, policy)
    assert len(used) == 3
    by_id = {r.memory_id: r.exclusion for r in used}
    assert by_id == {"a": "included", "b": "budget", "c": "filter"}


def test_apply_available_tokens_caps_usable_budget() -> None:
    from app.assemble import _apply_available_tokens
    from app.budget import TokenBudget

    base = TokenBudget(
        context_window=128_000,
        response_reserve=4096,
        safety_buffer=2560,
        usable_budget=8000,
        directive_tokens=10,
        messages_tokens=20,
        is_constrained=False,
        estimate_kind="chars_div_4",
    )
    capped = _apply_available_tokens(base, 100)
    assert capped.usable_budget == 100
    assert capped.is_constrained is True
    assert _apply_available_tokens(base, 0) is base
    assert _apply_available_tokens(base, 9000) is base
