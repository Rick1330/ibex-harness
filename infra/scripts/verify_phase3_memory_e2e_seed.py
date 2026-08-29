#!/usr/bin/env python3
"""SQL seed + assertion helpers for verify_phase3_memory_e2e.sh (m3.E.2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
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
from app.db import create_engine, create_session_factory  # noqa: E402
from app.vectorstore.pgvector_store import PgVectorStore  # noqa: E402
from tests.integration.conftest import with_service_org  # noqa: E402
from tests.integration.find_similar_support import (  # noqa: E402
    InsertScoredMemoryParams,
    SeedCompositeRankingParams,
    upsert_embedding,
)

DEV_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
DEV_AGENT_ID = UUID("00000000-0000-0000-0000-000000000003")


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


async def _session_stack() -> tuple[async_sessionmaker[AsyncSession], PgVectorStore]:
    dsn = _async_dsn()
    settings = Settings(database_url=dsn)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PgVectorStore(factory, settings)
    return factory, store


async def cmd_ranking_seed() -> None:
    org_id = UUID(os.getenv("IBEX_E2E_DEV_ORG_ID", str(DEV_ORG_ID)))
    agent_id = UUID(os.getenv("IBEX_E2E_DEV_AGENT_ID", str(DEV_AGENT_ID)))
    factory, store = await _session_stack()
    now = datetime.now(tz=UTC)
    factual_id = await _insert_scored_memory(
        factory,
        InsertScoredMemoryParams(
            org_id=org_id,
            agent_id=agent_id,
            content="composite ranking factual memory dark mode preference",
            category="factual",
            valid_from=now - timedelta(days=90),
        ),
    )
    episodic_id = await _insert_scored_memory(
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


async def _insert_scored_memory(
    session_factory: async_sessionmaker[AsyncSession],
    params: InsertScoredMemoryParams,
) -> UUID:
    memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, params.org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens,
                    category, confidence, usefulness_score, status, valid_from
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens,
                    :category, :confidence, :usefulness, :status, :valid_from
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(params.org_id),
                "agent_id": str(params.agent_id),
                "content": params.content,
                "hash": f"hash-{memory_id.hex}",
                "tokens": max(1, len(params.content.split())),
                "category": params.category,
                "confidence": params.confidence,
                "usefulness": params.usefulness_score,
                "status": params.status,
                "valid_from": params.valid_from,
            },
        )
    return memory_id


async def cmd_cascade_setup(memory_id: UUID, org_id: UUID, agent_id: UUID) -> None:
    factory, _ = await _session_stack()
    related_id = await _insert_related_memory(factory, org_id, agent_id)
    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memory_labels (memory_id, org_id, label, confidence)
                VALUES (:memory_id, :org_id, 'factual', 0.9)
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


async def _insert_related_memory(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    agent_id: UUID,
) -> UUID:
    memory_id = uuid4()
    async with session_factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "content": "phase3 e2e cascade related memory",
                "hash": f"hash-{memory_id.hex}",
                "tokens": 5,
            },
        )
    return memory_id


async def cmd_cascade_check(memory_id: UUID) -> None:
    factory, _ = await _session_stack()
    async with factory() as session:
        await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        label_count = (
            await session.execute(
                text(
                    "SELECT COUNT(*)::int AS c FROM ibex_core.memory_labels WHERE memory_id = :id"
                ),
                {"id": str(memory_id)},
            )
        ).one()
        rel_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c FROM ibex_core.memory_relationships
                    WHERE source_memory_id = :id OR target_memory_id = :id
                    """
                ),
                {"id": str(memory_id)},
            )
        ).one()
        esc_count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE new_memory_id = :id OR candidate_memory_id = :id
                    """
                ),
                {"id": str(memory_id)},
            )
        ).one()
    total = int(label_count.c) + int(rel_count.c) + int(esc_count.c)
    if total != 0:
        raise SystemExit(
            f"cascade-check failed: memory_id={memory_id} "
            f"labels={label_count.c} rels={rel_count.c} escalations={esc_count.c}"
        )


async def cmd_escalation_check(org_id: UUID, new_id: UUID, candidate_id: UUID) -> None:
    factory, _ = await _session_stack()
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 memory e2e seed helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ranking-seed", help="Insert composite-ranking pair for dev org/agent")

    cascade_setup = sub.add_parser("cascade-setup", help="Insert FK children for cascade test")
    cascade_setup.add_argument("--memory-id", type=UUID, required=True)
    cascade_setup.add_argument("--org-id", type=UUID, required=True)
    cascade_setup.add_argument("--agent-id", type=UUID, required=True)

    cascade_check = sub.add_parser("cascade-check", help="Assert zero FK children remain")
    cascade_check.add_argument("--memory-id", type=UUID, required=True)

    esc = sub.add_parser("escalation-check", help="Assert pending escalation row exists")
    esc.add_argument("--org-id", type=UUID, required=True)
    esc.add_argument("--new-id", type=UUID, required=True)
    esc.add_argument("--candidate-id", type=UUID, required=True)

    args = parser.parse_args()
    if args.command == "ranking-seed":
        asyncio.run(cmd_ranking_seed())
    elif args.command == "cascade-setup":
        asyncio.run(cmd_cascade_setup(args.memory_id, args.org_id, args.agent_id))
    elif args.command == "cascade-check":
        asyncio.run(cmd_cascade_check(args.memory_id))
    elif args.command == "escalation-check":
        asyncio.run(cmd_escalation_check(args.org_id, args.new_id, args.candidate_id))


if __name__ == "__main__":
    main()
