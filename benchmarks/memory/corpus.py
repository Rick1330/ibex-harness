"""Corpus seed / index helpers for HNSW benches (split from hnsw_bench)."""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from synth import unit_vector, vec_literal

_DIM = 1024
_COPY_CHUNK = 20_000
_HNSW_INDEX = "idx_memories_embedding_hnsw"
_SET_SERVICE_ACCOUNT = "SELECT set_config('app.is_service_account', 'true', true)"
_HNSW_CREATE_SQL = """
CREATE INDEX idx_memories_embedding_hnsw
    ON ibex_core.memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE status = 'active' AND deleted_at IS NULL
"""


def memory_id_for(org_id: UUID, idx: int) -> UUID:
    return uuid5(org_id, f"bench-{idx}")


async def exec_sql(
    session: AsyncSession, sql: str, params: dict[str, object] | None = None
) -> None:
    await session.execute(
        text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        params or {},
    )


async def scalar(
    engine: AsyncEngine, sql: str, params: dict[str, object] | None = None
) -> Any:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                _SET_SERVICE_ACCOUNT
            )
        )
        result = await conn.execute(
            text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            params or {},
        )
        return result.scalar()


async def reset_memories(engine: AsyncEngine) -> None:
    """TRUNCATE memories (+ dependent label/relationship rows) for a clean corpus."""
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                _SET_SERVICE_ACCOUNT
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.memories CASCADE"
            )
        )


async def analyze_memories(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                _SET_SERVICE_ACCOUNT
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "ANALYZE ibex_core.memories"
            )
        )


async def count_memories(engine: AsyncEngine) -> int:
    value = await scalar(engine, "SELECT count(*)::bigint FROM ibex_core.memories")
    return int(value or 0)


async def idx_scan_count(engine: AsyncEngine) -> int:
    await scalar(engine, "SELECT pg_stat_force_next_flush()")
    value = await scalar(
        engine,
        """
        SELECT coalesce(sum(idx_scan), 0)::bigint
        FROM pg_stat_all_indexes
        WHERE indexrelname = :name
        """,
        {"name": _HNSW_INDEX},
    )
    return int(value or 0)


async def ensure_hnsw_index(engine: AsyncEngine, *, maintenance_work_mem: str) -> None:
    exists = await scalar(
        engine,
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ibex_core' AND c.relname = :name
        """,
        {"name": _HNSW_INDEX},
    )
    if exists:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                _SET_SERVICE_ACCOUNT
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('maintenance_work_mem', :mwm, true)"
            ),
            {"mwm": maintenance_work_mem},
        )
        await conn.execute(
            text(_HNSW_CREATE_SQL)  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        )


async def drop_hnsw_index(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                _SET_SERVICE_ACCOUNT
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "DROP INDEX IF EXISTS ibex_core.idx_memories_embedding_hnsw"
            )
        )


async def try_prewarm(engine: AsyncEngine) -> bool:
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "CREATE EXTENSION IF NOT EXISTS pg_prewarm"
                )
            )
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT pg_prewarm('ibex_core.idx_memories_embedding_hnsw'::regclass)"
                )
            )
        return True
    except Exception as exc:  # noqa: BLE001 — optional extension
        print(f"  pg_prewarm skipped: {exc}", flush=True)
        return False


async def seed_org(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    org_id, user_id, agent_id = uuid4(), uuid4(), uuid4()
    slug = f"bench-{org_id.hex[:8]}"
    async with factory() as session, session.begin():
        await exec_sql(session, _SET_SERVICE_ACCOUNT)
        await exec_sql(
            session,
            """
            INSERT INTO ibex_core.organizations (id, name, slug)
            VALUES (:id, :name, :slug)
            """,
            {"id": str(org_id), "name": f"Bench {slug}", "slug": slug},
        )
        await exec_sql(
            session,
            """
            INSERT INTO ibex_core.users (id, org_id, email, name)
            VALUES (:id, :org_id, :email, :name)
            """,
            {
                "id": str(user_id),
                "org_id": str(org_id),
                "email": f"{slug}@example.com",
                "name": "Bench",
            },
        )
        await exec_sql(
            session,
            """
            INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
            VALUES (:id, :org_id, :created_by, :name, :slug)
            """,
            {
                "id": str(agent_id),
                "org_id": str(org_id),
                "created_by": str(user_id),
                "name": "BenchAgent",
                "slug": f"agent-{agent_id.hex[:8]}",
            },
        )
    return org_id, agent_id


async def bulk_insert_memories(
    engine: AsyncEngine,
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
) -> None:
    """Seed via asyncpg text/CSV COPY in chunks (pgvector has no binary encoder)."""
    columns = [
        "id",
        "org_id",
        "agent_id",
        "content",
        "content_hash",
        "content_tokens",
        "embedding",
        "embedding_model",
        "embedding_dim",
        "status",
    ]

    total = size
    for start in range(0, total, _COPY_CHUNK):
        end = min(total, start + _COPY_CHUNK)
        text_buf = StringIO()
        writer = csv.writer(text_buf)
        for idx in range(start, end):
            mid = memory_id_for(org_id, idx)
            writer.writerow(
                [
                    str(mid),
                    str(org_id),
                    str(agent_id),
                    f"bench-{mid.hex}",
                    f"h-{mid.hex}",
                    1,
                    vec_literal(unit_vector(idx)),
                    "bench-synthetic",
                    _DIM,
                    "active",
                ]
            )
        payload = BytesIO(text_buf.getvalue().encode("utf-8"))
        del text_buf

        async with engine.begin() as conn:
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    _SET_SERVICE_ACCOUNT
                )
            )
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('app.current_org_id', :org_id, true)"
                ),
                {"org_id": str(org_id)},
            )
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('synchronous_commit', 'off', true)"
                )
            )
            raw = await conn.get_raw_connection()
            driver = raw.driver_connection
            if driver is None:
                raise RuntimeError("asyncpg driver_connection missing for COPY")
            await driver.copy_to_table(
                "memories",
                source=payload,
                columns=columns,
                schema_name="ibex_core",
                format="csv",
            )
        print(f"  seeded {end}/{total}", flush=True)
