"""Integration: the v2 corpus loads with graded vectors and pending conflicts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RANK_DIR = _REPO_ROOT / "benchmarks" / "memory" / "ranking_quality"
for _path in (_REPO_ROOT / "services" / "memory", _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import seed  # noqa: E402

pytestmark = pytest.mark.asyncio

CORPUS = _RANK_DIR / "gold_set_v2.json"
EXPECTED_MEMORIES = 500
EXPECTED_PENDING_CONFLICTS = 40


async def _org_session(session_factory):
    session = session_factory()
    await session.__aenter__()
    await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org, true)"),
        {"org": str(seed.GOLD_ORG_ID)},
    )
    return session


async def test_v2_corpus_seeds_with_graded_vectors_and_pending_conflicts(
    session_factory, store
) -> None:
    result = await seed.seed_gold_set(session_factory, store, gold_path=CORPUS)

    assert len(result.content_key_to_memory_id) == EXPECTED_MEMORIES

    session = await _org_session(session_factory)
    try:
        pending = await session.execute(
            text(
                """
                SELECT count(*) FROM ibex_core.memory_conflict_escalations
                WHERE org_id = :org AND status = 'pending'
                """
            ),
            {"org": str(seed.GOLD_ORG_ID)},
        )
        assert pending.scalar_one() == EXPECTED_PENDING_CONFLICTS
    finally:
        await session.__aexit__(None, None, None)

    # The stored vector must reproduce the designed cosine, not merely exist: the winner is
    # 1.0 against its topic and the twin is 0.80 by construction.
    session = await _org_session(session_factory)
    try:
        for key, expected in (("gold.current.40.0", 1.0), ("gold.twin.40.0", 0.8)):
            memory_id = result.content_key_to_memory_id[key]
            cosine = await session.execute(
                text(
                    """
                    SELECT 1 - (embedding <=> CAST(:probe AS vector))
                    FROM ibex_core.memories
                    WHERE id = :id AND org_id = :org
                    """
                ),
                {
                    "probe": _vector_literal("default branch name"),
                    "id": str(memory_id),
                    "org": str(seed.GOLD_ORG_ID),
                },
            )
            assert cosine.scalar_one() == pytest.approx(expected, abs=1e-6)
    finally:
        await session.__aexit__(None, None, None)


def _vector_literal(topic: str) -> str:
    """Probe in the corpus's own basis space: the index matters, not just the topic name."""
    import json

    from profiles import profile_vector

    topics = json.loads(CORPUS.read_text(encoding="utf-8"))["topics"]
    vector = profile_vector({topic: 1.0}, topics, dim=1024)
    return "[" + ",".join(f"{value:.9f}" for value in vector) + "]"
