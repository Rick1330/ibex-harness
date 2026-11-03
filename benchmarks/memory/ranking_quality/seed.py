"""Seed ranking-quality gold set into Postgres (dedicated org namespace)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from app.vectorstore.pgvector_store import PgVectorStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.integration.conftest import with_service_org, zero_embedding
from tests.integration.find_similar_support import (
    InsertScoredMemoryParams,
    insert_scored_memory,
    upsert_embedding,
)

GOLD_ORG_ID = UUID("11111111-2222-3333-4444-555555555501")
GOLD_AGENT_ID = UUID("11111111-2222-3333-4444-555555555502")
GOLD_USER_ID = UUID("11111111-2222-3333-4444-555555555503")
GOLD_SET_PATH = Path(__file__).resolve().parent / "gold_set_v1.json"
_RANK_DIR = GOLD_SET_PATH.parent
_BENCH_MEMORY = _RANK_DIR.parent
_SERVICE_ACCOUNT_SQL = "SELECT set_config('app.is_service_account', 'true', true)"

if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))

from path_guard import resolve_bench_input_path
from profiles import profile_vector
from validate_gold_set import validate_gold_set
from validate_gold_set_v2 import validate_gold_set_v2


@dataclass(frozen=True, slots=True)
class GoldSeedResult:
    org_id: UUID
    agent_id: UUID
    content_key_to_memory_id: dict[str, UUID]


def load_gold_set(path: Path | None = None) -> dict:
    payload_path = path or GOLD_SET_PATH
    resolved = resolve_bench_input_path(payload_path, bench_dir=_RANK_DIR)
    return json.loads(resolved.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083


def _raise_validation_errors(errors: list[str]) -> None:
    if not errors:
        return
    joined = "\n".join(f"  - {e}" for e in errors)
    raise ValueError(f"gold set validation failed:\n{joined}")


def _parse_memory_rows(memories: object) -> list[dict]:
    if not isinstance(memories, list) or not memories:
        msg = "gold set memories must be a non-empty array"
        raise ValueError(msg)
    rows: list[dict] = []
    for row in memories:
        if not isinstance(row, dict):
            msg = "memory row must be an object"
            raise ValueError(msg)
        rows.append(row)
    return rows


async def _ensure_org_agent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(_SERVICE_ACCOUNT_SQL)  # nosemgrep
        )
        await with_service_org(session, GOLD_ORG_ID)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (:id, :name, :slug)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": str(GOLD_ORG_ID),
                "name": "Ranking Gold Org",
                "slug": "ranking-gold-org",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.users (id, org_id, email, name)
                VALUES (:id, :org_id, :email, :name)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": str(GOLD_USER_ID),
                "org_id": str(GOLD_ORG_ID),
                "email": "ranking-gold@example.com",
                "name": "Gold User",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
                VALUES (:id, :org_id, :created_by, :name, :slug)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": str(GOLD_AGENT_ID),
                "org_id": str(GOLD_ORG_ID),
                "created_by": str(GOLD_USER_ID),
                "name": "Gold Agent",
                "slug": "ranking-gold-agent",
            },
        )


async def _purge_org_memories(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(_SERVICE_ACCOUNT_SQL)  # nosemgrep
        )
        await with_service_org(session, GOLD_ORG_ID)
        await session.execute(
            text(
                """
                DELETE FROM ibex_core.memories
                WHERE org_id = :org_id
                """
            ),
            {"org_id": str(GOLD_ORG_ID)},
        )


async def _seed_memory_row(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    row: dict,
    *,
    now: datetime,
    topics: dict[str, int] | None = None,
) -> tuple[str, UUID]:
    content_key = str(row["content_key"])
    age_days = int(row.get("valid_from_days_ago", 30))
    memory_id = await insert_scored_memory(
        session_factory,
        InsertScoredMemoryParams(
            org_id=GOLD_ORG_ID,
            agent_id=GOLD_AGENT_ID,
            content=str(row["content"]),
            category=str(row["category"]),
            valid_from=now - timedelta(days=age_days),
            confidence=float(row.get("confidence", 0.85)),
            usefulness_score=float(row.get("usefulness_score", 0.5)),
            retrieval_count=int(row.get("retrieval_count", 0)),
        ),
    )
    embedding = _embedding_for_row(row, topics)
    if embedding is None:
        hotspot = int(row.get("embedding_hotspot", 0))
        if hotspot < 0 or hotspot >= len(zero_embedding()):
            msg = f"embedding_hotspot out of range for {content_key}"
            raise ValueError(msg)
    else:
        hotspot = 0
    await upsert_embedding(
        store,
        session_factory,
        org_id=GOLD_ORG_ID,
        memory_id=memory_id,
        hotspot=hotspot,
        embedding=embedding,
    )
    return content_key, memory_id


def _validated_payload(gold_path: Path | None) -> dict:
    payload = load_gold_set(gold_path)
    validator = validate_gold_set_v2 if payload.get("schema_version") == 2 else validate_gold_set
    _raise_validation_errors(validator(payload))
    return payload


def _validated_memories(gold_path: Path | None) -> list[dict]:
    return _parse_memory_rows(_validated_payload(gold_path)["memories"])


def _embedding_for_row(row: dict, topics: dict[str, int] | None) -> list[float] | None:
    """Vector for a gold row, or ``None`` when the row uses the v1 one-hot hotspot.

    v2 rows carry `embedding_profile`, a weighted combination of declared topic bases; the
    geometry only means anything if the stored vector is exactly that combination, so it is
    built here rather than approximated by a hotspot.
    """
    profile = row.get("embedding_profile")
    if profile is None:
        return None
    if not topics:
        msg = f"{row.get('content_key')!r} has an embedding_profile but the corpus declares no topics"
        raise ValueError(msg)
    return profile_vector(profile, topics)


def _conflict_pairs(memories: list[dict]) -> list[tuple[str, str]]:
    """(winner, twin) pairs declared by `conflicts_with`, in corpus order."""
    return [
        (str(row["content_key"]), str(twin))
        for row in memories
        for twin in row.get("conflicts_with") or []
    ]


async def _seed_memory_rows(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    memories: list[dict],
    *,
    now: datetime,
    topics: dict[str, int] | None = None,
) -> dict[str, UUID]:
    content_key_to_id: dict[str, UUID] = {}
    for row in memories:
        content_key, memory_id = await _seed_memory_row(
            session_factory, store, row, now=now, topics=topics
        )
        content_key_to_id[content_key] = memory_id
    return content_key_to_id


async def _seed_conflicts(
    session_factory: async_sessionmaker[AsyncSession],
    pairs: list[tuple[str, str]],
    content_key_to_id: dict[str, UUID],
) -> None:
    """Write one pending escalation per declared pair.

    Conflict suppression drops the lower-ranked side of a *pending* escalation
    (`read/conflicts.py`), so without these rows the graph subset measures nothing.
    """
    if not pairs:
        return
    async with session_factory() as session, session.begin():
        await session.execute(text(_SERVICE_ACCOUNT_SQL))  # nosemgrep
        await with_service_org(session, GOLD_ORG_ID)
        for winner, twin in pairs:
            await session.execute(
                text(
                    """
                    INSERT INTO ibex_core.memory_conflict_escalations
                        (org_id, new_memory_id, candidate_memory_id, conflict_type, status)
                    VALUES (:org_id, :new_memory_id, :candidate_memory_id, 'contradicts', 'pending')
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "org_id": str(GOLD_ORG_ID),
                    "new_memory_id": str(content_key_to_id[winner]),
                    "candidate_memory_id": str(content_key_to_id[twin]),
                },
            )


async def _analyze_memories(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(_SERVICE_ACCOUNT_SQL)  # nosemgrep
        )
        await with_service_org(session, GOLD_ORG_ID)
        await session.execute(text("ANALYZE ibex_core.memories"))  # nosemgrep


async def seed_gold_set(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    *,
    gold_path: Path | None = None,
) -> GoldSeedResult:
    """Insert gold memories + embeddings; return content_key → memory_id map."""
    payload = _validated_payload(gold_path)
    memories = _parse_memory_rows(payload["memories"])
    topics = payload.get("topics")
    await _ensure_org_agent(session_factory)
    await _purge_org_memories(session_factory)
    content_key_to_id = await _seed_memory_rows(
        session_factory,
        store,
        memories,
        now=datetime.now(tz=UTC),
        topics=topics,
    )
    await _seed_conflicts(session_factory, _conflict_pairs(memories), content_key_to_id)
    await _analyze_memories(session_factory)
    return GoldSeedResult(
        org_id=GOLD_ORG_ID,
        agent_id=GOLD_AGENT_ID,
        content_key_to_memory_id=content_key_to_id,
    )
