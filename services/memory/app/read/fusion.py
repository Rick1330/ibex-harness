"""Reciprocal Rank Fusion for hybrid memory retrieval (phase 5.A.1 + 5.A.2).

RRF combines ranked lists without comparing their scores, which is exactly the
problem here: cosine similarity and ``ts_rank_cd`` live on different scales, so
any weighted sum of the two needs a normalisation nobody can defend. RRF only
needs the ranks:

    score(d) = sum over channels of 1 / (k + rank_channel(d))

``k = 60`` is the value fixed in the original paper (Cormack, Clarke, Büttcher,
SIGIR 2009) and the default ``rank_constant`` in Elasticsearch's ``rrf``
retriever, so it is a defensible default rather than a tuned constant.

Ranks start at 1. A document that appears in both channels sums both terms,
which is why a hit both retrievers agree on outranks a hit only one found.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

RRF_K_DEFAULT: Final[int] = 60


@dataclass(frozen=True, slots=True)
class FusedRank:
    """One memory's fusion rank and the channels that contributed to it."""

    memory_id: UUID
    score: float
    channels: tuple[str, ...]


def reciprocal_rank_fusion(
    channels: Sequence[Sequence[UUID]],
    *,
    k: int = RRF_K_DEFAULT,
) -> list[FusedRank]:
    """Fuse ranked id lists into one deterministic ordering.

    Ties are broken by the memory id so the same inputs always produce the same
    order, which keeps pagination and tests stable.
    """
    if k < 1:
        msg = "RRF k must be >= 1"
        raise ValueError(msg)

    scores: dict[UUID, float] = {}
    seen_in: dict[UUID, list[str]] = {}
    for channel_index, ranked in enumerate(channels):
        for position, memory_id in enumerate(ranked, start=1):
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (k + position)
            label = str(channel_index)
            seen_in.setdefault(memory_id, []).append(label)

    fused = [
        FusedRank(
            memory_id=memory_id,
            score=score,
            channels=tuple(seen_in[memory_id]),
        )
        for memory_id, score in scores.items()
    ]
    fused.sort(key=lambda item: (-item.score, str(item.memory_id)))
    return fused
