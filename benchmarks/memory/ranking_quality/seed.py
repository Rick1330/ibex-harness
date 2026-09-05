"""Seed ranking-quality gold set into Postgres (dedicated org namespace)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.vectorstore.pgvector_store import PgVectorStore
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

from path_guard import resolve_bench_input_path  # noqa: E402
from validate_gold_set import validate_gold_set  # noqa: E402


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
    hotspot = int(row.get("embedding_hotspot", 0))
    if hotspot < 0 or hotspot >= len(zero_embedding()):
        msg = f"embedding_hotspot out of range for {content_key}"
        raise ValueError(msg)
    await upsert_embedding(store, org_id=GOLD_ORG_ID, memory_id=memory_id, hotspot=hotspot)
    return content_key, memory_id


def _validated_memories(gold_path: Path | None) -> list[dict]:
    payload = load_gold_set(gold_path)
    _raise_validation_errors(validate_gold_set(payload))
    return _parse_memory_rows(payload["memories"])


async def _seed_memory_rows(
    session_factory: async_sessionmaker[AsyncSession],
    store: PgVectorStore,
    memories: list[dict],
    *,
    now: datetime,
) -> dict[str, UUID]:
    content_key_to_id: dict[str, UUID] = {}
    for row in memories:
        content_key, memory_id = await _seed_memory_row(
            session_factory, store, row, now=now
        )
        content_key_to_id[content_key] = memory_id
    return content_key_to_id


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
    memories = _validated_memories(gold_path)
    await _ensure_org_agent(session_factory)
    await _purge_org_memories(session_factory)
    content_key_to_id = await _seed_memory_rows(
        session_factory,
        store,
        memories,
        now=datetime.now(tz=UTC),
    )
    await _analyze_memories(session_factory)
    return GoldSeedResult(
        org_id=GOLD_ORG_ID,
        agent_id=GOLD_AGENT_ID,
        content_key_to_memory_id=content_key_to_id,
    )
