#!/usr/bin/env python3
"""SQL seed + assertion helpers for verify_phase3_memory_e2e.sh (m3.E.2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

_ROOT = Path(__file__).resolve().parents[2]
_MEMORY_DIR = _ROOT / "services" / "memory"
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.config import Settings  # noqa: E402
from app.dedup.hash import content_hash_sha256  # noqa: E402
from app.db import create_engine, create_session_factory  # noqa: E402
from app.vectorstore.base import UpsertRequest  # noqa: E402
from app.vectorstore.pgvector_store import PgVectorStore  # noqa: E402
from tests.integration.conftest import TimedMemorySeed, insert_timed_memory, with_service_org  # noqa: E402
from tests.integration.find_similar_support import (  # noqa: E402
    InsertActiveMemoryParams,
    InsertScoredMemoryParams,
    SeedCompositeRankingParams,
    insert_active_memory,
    insert_scored_memory,
    upsert_embedding,
)


def _async_dsn() -> str:
    raw = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_DSN") or os.getenv(
        "POSTGRES_TEST_DSN"
    )
    if not raw:
        raise SystemExit("POSTGRES_DSN or IBEX_MEMORY_DATABASE_URL required")
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


def _session_stack() -> tuple[async_sessionmaker[AsyncSession], PgVectorStore]:
    dsn = _async_dsn()
    settings = Settings(database_url=dsn)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PgVectorStore(factory, settings)
    return factory, store


async def _fetch_embeddings(texts: list[str]) -> list[list[float]]:
    import httpx

    base = os.environ["EMBEDDER_ADDR"].rstrip("/")
    token = os.environ["EMBED_TOKEN"]
    org = os.environ["DEV_ORG"]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base}/v1/embed",
            headers={"Authorization": f"Bearer {token}"},
            json={"texts": texts, "org_id": org},
        )
    if response.status_code != 200:
        raise SystemExit(f"embedder returned {response.status_code} for e2e seed embed")
    return response.json()["vectors"]


async def cmd_supersede_seed(org_id: UUID, agent_id: UUID, old_content: str) -> None:
    """Seed memory A with closed interval + stub embedding (HTTP cannot set valid_from)."""
    factory, store = _session_stack()
    march = datetime(2026, 3, 1, tzinfo=UTC)
    june = datetime(2026, 6, 1, tzinfo=UTC)
    old_id = uuid4()
    await insert_timed_memory(
        factory,
        TimedMemorySeed(
            org_id=org_id,
            agent_id=agent_id,
            memory_id=old_id,
            content=old_content,
            content_hash=content_hash_sha256(old_content),
            valid_from=march,
            valid_until=june,
        ),
    )
    embedding = (await _fetch_embeddings([old_content]))[0]
    await store.upsert(
        UpsertRequest(
            memory_id=old_id,
            org_id=org_id,
            embedding=embedding,
            embedding_model="BAAI/bge-m3",
        )
    )
    print(json.dumps({"old_id": str(old_id), "valid_until": june.isoformat()}))


async def cmd_supersede_check(org_id: UUID, old_id: UUID, new_id: UUID) -> None:
    factory, _ = _session_stack()
    async with factory() as session:
        await with_service_org(session, org_id)
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, superseded_by::text AS tip
                    FROM ibex_core.memories
                    WHERE id = :old_id AND org_id = :org_id
                    """
                ),
                {"old_id": str(old_id), "org_id": str(org_id)},
            )
        ).one()
        rel = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_relationships
                    WHERE org_id = :org_id
                      AND source_memory_id = :new_id
                      AND target_memory_id = :old_id
                      AND relationship_type = 'supersedes'
                    """
                ),
                {
                    "org_id": str(org_id),
                    "old_id": str(old_id),
                    "new_id": str(new_id),
                },
            )
        ).one()
        esc = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE org_id = :org_id
                      AND new_memory_id = :new_id
                      AND candidate_memory_id = :old_id
                      AND status = 'pending'
                    """
                ),
                {
                    "org_id": str(org_id),
                    "new_id": str(new_id),
                    "old_id": str(old_id),
                },
            )
        ).one()
    _require_supersede_row(row, old_id=old_id, new_id=new_id)
    _require_count(rel.c, want=1, label="supersedes edge")
    _require_count(esc.c, want=0, label="pending escalations")


def _require_supersede_row(row: object, *, old_id: UUID, new_id: UUID) -> None:
    status = getattr(row, "status", None)
    tip = getattr(row, "tip", None)
    if status != "superseded":
        raise SystemExit(f"supersede-check: old memory status={status!r}, want superseded")
    if tip != str(new_id):
        raise SystemExit(f"supersede-check: superseded_by={tip!r}, want {new_id}")


def _require_count(actual: int, *, want: int, label: str) -> None:
    if int(actual) != want:
        raise SystemExit(f"supersede-check: expected {want} {label}, got {actual}")


def _redis_url() -> str:
    url = os.getenv("REDIS_URL") or os.getenv("IBEX_MEMORY_REDIS_URL")
    if not url:
        raise SystemExit("REDIS_URL required for redis-cache-check")
    return url


async def _fetch_redis_cache_keys(
    org_id: UUID, agent_id: UUID, memory_id: UUID
) -> tuple[bytes | None, float | None]:
    from redis.asyncio import Redis

    object_key = f"{org_id}:memory:{memory_id}"
    hot_key = f"{org_id}:hot_memories:{agent_id}"
    redis = Redis.from_url(_redis_url())
    try:
        cached = await redis.get(object_key)
        zscore = await redis.zscore(hot_key, str(memory_id))
    finally:
        await redis.aclose()
    return cached, zscore


def _assert_redis_before_delete(cached: bytes | None, zscore: float | None, memory_id: UUID) -> None:
    if cached is None:
        raise SystemExit(f"redis-cache-check: expected object cache for {memory_id}")
    if zscore is None:
        raise SystemExit(f"redis-cache-check: expected hot ZSET member for {memory_id}")


def _assert_redis_after_delete(cached: bytes | None, zscore: float | None) -> None:
    if cached is None or zscore is None:
        raise SystemExit(
            "redis-cache-check: expected stale cache entries after SQL DELETE "
            f"(object={cached is not None} zset={zscore is not None})"
        )


async def cmd_redis_cache_check(
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    *,
    phase: str,
) -> None:
    cached, zscore = await _fetch_redis_cache_keys(org_id, agent_id, memory_id)
    if phase == "before-delete":
        _assert_redis_before_delete(cached, zscore, memory_id)
        return
    if phase == "after-delete":
        _assert_redis_after_delete(cached, zscore)
        return
    raise SystemExit(f"redis-cache-check: unknown phase {phase!r}")


async def cmd_hot_cache_read_check(
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    *,
    expect_absent: bool,
) -> None:
    """Exercise MemoryHotCacheReader hydrate path (no dedicated HTTP route today)."""
    from redis.asyncio import Redis

    from app.read.hot_cache import MemoryHotCacheReader
    from app.read.models import HotMemoryQuery

    factory, _ = _session_stack()
    redis = Redis.from_url(_redis_url())
    try:
        reader = MemoryHotCacheReader(redis, factory)
        results = await reader.get_hot_memories(
            HotMemoryQuery(org_id=org_id, agent_id=agent_id, limit=50, min_confidence=0.0)
        )
    finally:
        await redis.aclose()
    returned_ids = {result.id for result in results}
    if expect_absent and memory_id in returned_ids:
        raise SystemExit(
            f"hot-cache-read-check: deleted memory {memory_id} present in hydrate results"
        )


async def cmd_ranking_seed(org_id: UUID, agent_id: UUID) -> None:
    factory, store = _session_stack()
    now = datetime.now(tz=UTC)
    factual_id = await insert_scored_memory(
        factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="composite ranking factual memory dark mode preference",
            category="factual",
            valid_from=now - timedelta(days=90),
        ),
    )
    episodic_id = await insert_scored_memory(
        factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="composite ranking episodic memory dark mode preference",
            category="episodic",
            valid_from=now - timedelta(days=14),
        ),
    )
    hotspot = SeedCompositeRankingParams().hotspot
    await upsert_embedding(store, org_id=org_id, memory_id=factual_id, hotspot=hotspot)
    await upsert_embedding(store, org_id=org_id, memory_id=episodic_id, hotspot=hotspot)
    print(
        json.dumps(
            {
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "factual_id": str(factual_id),
                "episodic_id": str(episodic_id),
            }
        )
    )


async def cmd_cascade_setup(memory_id: UUID, org_id: UUID, agent_id: UUID) -> None:
    factory, _ = _session_stack()
    related_id = await insert_active_memory(
        factory,
        InsertActiveMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="phase3 e2e cascade related memory",
        ),
    )
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_labels (memory_id, org_id, label, confidence)
                VALUES (:memory_id, :org_id, 'preference', 0.9)
                ON CONFLICT (memory_id, label) DO NOTHING
                """
            ),
            {"memory_id": str(memory_id), "org_id": str(org_id)},
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_relationships (
                    org_id, source_memory_id, target_memory_id, relationship_type
                ) VALUES (
                    :org_id, :source_id, :target_id, 'supersedes'
                )
                """
            ),
            {
                "org_id": str(org_id),
                "source_id": str(memory_id),
                "target_id": str(related_id),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_conflict_escalations (
                    org_id, new_memory_id, candidate_memory_id, conflict_type, status
                ) VALUES (
                    :org_id, :new_id, :candidate_id, 'contradiction', 'pending'
                )
                """
            ),
            {
                "org_id": str(org_id),
                "new_id": str(memory_id),
                "candidate_id": str(related_id),
            },
        )


async def cmd_fixture_cleanup(org_id: UUID, agent_id: UUID) -> None:
    """Remove all memories for the dev seed agent so repeated e2e runs are idempotent."""
    factory, _ = _session_stack()
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                DELETE FROM ibex_core.memories
                WHERE org_id = :org_id AND agent_id = :agent_id
                """
            ),
            {"org_id": str(org_id), "agent_id": str(agent_id)},
        )


async def cmd_cascade_check(memory_id: UUID, org_id: UUID) -> None:
    factory, _ = _session_stack()
    async with factory() as session:
        await with_service_org(session, org_id)
        label_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c FROM ibex_core.memory_labels
                    WHERE memory_id = :id AND org_id = :org_id
                    """
                ),
                {"id": str(memory_id), "org_id": str(org_id)},
            )
        ).one()
        rel_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c FROM ibex_core.memory_relationships
                    WHERE org_id = :org_id
                      AND (source_memory_id = :id OR target_memory_id = :id)
                    """
                ),
                {"id": str(memory_id), "org_id": str(org_id)},
            )
        ).one()
        esc_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE org_id = :org_id
                      AND (new_memory_id = :id OR candidate_memory_id = :id)
                    """
                ),
                {"id": str(memory_id), "org_id": str(org_id)},
            )
        ).one()
    total = int(label_count.c) + int(rel_count.c) + int(esc_count.c)
    if total != 0:
        raise SystemExit(
            f"cascade-check failed: memory_id={memory_id} "
            f"labels={label_count.c} rels={rel_count.c} escalations={esc_count.c}"
        )


async def cmd_escalation_check(org_id: UUID, new_id: UUID, candidate_id: UUID) -> None:
    factory, _ = _session_stack()
    async with factory() as session:
        await with_service_org(session, org_id)
        count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE org_id = :org AND new_memory_id = :new_id
                      AND candidate_memory_id = :candidate
                      AND status = 'pending'
                    """
                ),
                {
                    "org": str(org_id),
                    "new_id": str(new_id),
                    "candidate": str(candidate_id),
                },
            )
        ).one()
    if int(count.c) != 1:
        raise SystemExit(
            f"escalation-check failed: expected 1 pending row, got {count.c} "
            f"(new={new_id} candidate={candidate_id})"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3 memory e2e seed helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    ranking = sub.add_parser("ranking-seed", help="Insert composite-ranking pair for dev org/agent")
    ranking.add_argument("--org-id", type=UUID, required=True)
    ranking.add_argument("--agent-id", type=UUID, required=True)

    fixture_cleanup = sub.add_parser(
        "fixture-cleanup",
        help="Delete all memories for dev org/agent (idempotent e2e runs)",
    )
    fixture_cleanup.add_argument("--org-id", type=UUID, required=True)
    fixture_cleanup.add_argument("--agent-id", type=UUID, required=True)

    cascade_setup = sub.add_parser("cascade-setup", help="Insert FK children for cascade test")
    cascade_setup.add_argument("--memory-id", type=UUID, required=True)
    cascade_setup.add_argument("--org-id", type=UUID, required=True)
    cascade_setup.add_argument("--agent-id", type=UUID, required=True)

    cascade_check = sub.add_parser("cascade-check", help="Assert zero FK children remain")
    cascade_check.add_argument("--memory-id", type=UUID, required=True)
    cascade_check.add_argument("--org-id", type=UUID, required=True)

    esc = sub.add_parser("escalation-check", help="Assert pending escalation row exists")
    esc.add_argument("--org-id", type=UUID, required=True)
    esc.add_argument("--new-id", type=UUID, required=True)
    esc.add_argument("--candidate-id", type=UUID, required=True)

    supersede_seed = sub.add_parser(
        "supersede-seed",
        help="SQL-seed memory A with closed interval + stub embedding",
    )
    supersede_seed.add_argument("--org-id", type=UUID, required=True)
    supersede_seed.add_argument("--agent-id", type=UUID, required=True)
    supersede_seed.add_argument("--old-content", required=True)

    supersede_check = sub.add_parser(
        "supersede-check",
        help="Assert auto-supersede: status, edge, no escalation",
    )
    supersede_check.add_argument("--org-id", type=UUID, required=True)
    supersede_check.add_argument("--old-id", type=UUID, required=True)
    supersede_check.add_argument("--new-id", type=UUID, required=True)

    redis_cache = sub.add_parser(
        "redis-cache-check",
        help="Assert Redis object cache + hot ZSET state",
    )
    redis_cache.add_argument("--org-id", type=UUID, required=True)
    redis_cache.add_argument("--agent-id", type=UUID, required=True)
    redis_cache.add_argument("--memory-id", type=UUID, required=True)
    redis_cache.add_argument(
        "--phase",
        choices=("before-delete", "after-delete"),
        required=True,
    )

    hot_cache_read = sub.add_parser(
        "hot-cache-read-check",
        help="MemoryHotCacheReader hydrate path — assert memory id presence",
    )
    hot_cache_read.add_argument("--org-id", type=UUID, required=True)
    hot_cache_read.add_argument("--agent-id", type=UUID, required=True)
    hot_cache_read.add_argument("--memory-id", type=UUID, required=True)
    hot_cache_read.add_argument("--expect-absent", action="store_true")
    return parser


async def _run_ranking_seed(args: argparse.Namespace) -> None:
    await cmd_ranking_seed(args.org_id, args.agent_id)


async def _run_fixture_cleanup(args: argparse.Namespace) -> None:
    await cmd_fixture_cleanup(args.org_id, args.agent_id)


async def _run_cascade_setup(args: argparse.Namespace) -> None:
    await cmd_cascade_setup(args.memory_id, args.org_id, args.agent_id)


async def _run_cascade_check(args: argparse.Namespace) -> None:
    await cmd_cascade_check(args.memory_id, args.org_id)


async def _run_escalation_check(args: argparse.Namespace) -> None:
    await cmd_escalation_check(args.org_id, args.new_id, args.candidate_id)


async def _run_supersede_seed(args: argparse.Namespace) -> None:
    await cmd_supersede_seed(args.org_id, args.agent_id, args.old_content)


async def _run_supersede_check(args: argparse.Namespace) -> None:
    await cmd_supersede_check(args.org_id, args.old_id, args.new_id)


async def _run_redis_cache_check(args: argparse.Namespace) -> None:
    await cmd_redis_cache_check(
        args.org_id, args.agent_id, args.memory_id, phase=args.phase
    )


async def _run_hot_cache_read_check(args: argparse.Namespace) -> None:
    await cmd_hot_cache_read_check(
        args.org_id,
        args.agent_id,
        args.memory_id,
        expect_absent=args.expect_absent,
    )


_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], Awaitable[None]]] = {
    "ranking-seed": _run_ranking_seed,
    "fixture-cleanup": _run_fixture_cleanup,
    "cascade-setup": _run_cascade_setup,
    "cascade-check": _run_cascade_check,
    "escalation-check": _run_escalation_check,
    "supersede-seed": _run_supersede_seed,
    "supersede-check": _run_supersede_check,
    "redis-cache-check": _run_redis_cache_check,
    "hot-cache-read-check": _run_hot_cache_read_check,
}


def main() -> None:
    args = _build_parser().parse_args()
    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        raise SystemExit(f"unknown command {args.command!r}")
    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
