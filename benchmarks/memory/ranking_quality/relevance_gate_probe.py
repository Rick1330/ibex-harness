"""Opened-retrieval relevance-gate probe for ranking-quality gold set (m3.5.C.3)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.repository import MemoryReadRepository
from tests.integration.conftest import zero_embedding

GATE_BAIT_KEY = "gold.noise.relevance_gate_bait"
GATE_RELEVANT_KEY = "gold.factual.notification_channel"
GATE_PROBE_LIMIT = 50


class _GoldSeedLike(Protocol):
    org_id: UUID
    agent_id: UUID


class _QueryEvalLike(Protocol):
    seed: _GoldSeedLike
    id_to_key: dict[str, str]
    mem_by_key: dict[str, dict]


def _require_gold_memory(ctx: _QueryEvalLike, content_key: str, *, role: str) -> None:
    if content_key in ctx.mem_by_key:
        return
    msg = f"gold set missing gate probe {role} memory {content_key!r}"
    raise RuntimeError(msg)


def _assert_gate_probe_ranking(
    ranked_keys: list[str],
    *,
    bait_key: str,
    relevant_key: str,
) -> None:
    if bait_key in ranked_keys:
        msg = (
            "relevance gate probe failed: bait "
            f"{bait_key!r} appeared in ranked results under min_similarity=0.0"
        )
        raise RuntimeError(msg)
    if relevant_key not in ranked_keys:
        msg = (
            "relevance gate probe failed: expected relevant "
            f"{relevant_key!r} missing from ranked results"
        )
        raise RuntimeError(msg)


def _ranked_content_keys(
    results: list[MemorySearchResult],
    id_to_key: dict[str, str],
) -> list[str]:
    return [
        id_to_key[str(hit.id)] for hit in results if str(hit.id) in id_to_key
    ]


async def evaluate_relevance_gate_probe(
    repo: MemoryReadRepository,
    ctx: _QueryEvalLike,
) -> dict:
    """Open retrieval so orthogonal bait reaches scoring; fail unless excluded."""
    _require_gold_memory(ctx, GATE_BAIT_KEY, role="bait")
    _require_gold_memory(ctx, GATE_RELEVANT_KEY, role="relevant")
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=ctx.seed.org_id,
            agent_id=ctx.seed.agent_id,
            query_embedding=zero_embedding(hotspot=1),
            query_text="notification preferences relevance gate probe",
            limit=GATE_PROBE_LIMIT,
            min_similarity=0.0,
        )
    )
    ranked_keys = _ranked_content_keys(results, ctx.id_to_key)
    _assert_gate_probe_ranking(
        ranked_keys, bait_key=GATE_BAIT_KEY, relevant_key=GATE_RELEVANT_KEY
    )
    return {
        "bait_content_key": GATE_BAIT_KEY,
        "relevant_content_key": GATE_RELEVANT_KEY,
        "min_similarity": 0.0,
        "limit": GATE_PROBE_LIMIT,
        "bait_excluded": True,
        "relevant_present": True,
        "ranked_count": len(ranked_keys),
    }
