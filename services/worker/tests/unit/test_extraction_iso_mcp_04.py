"""ISO-MCP-04: forged extraction org_id must not read/write Org B session."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.extraction import session_store as session_store_mod
from app.extraction.batch import BatchJob, TurnPayload, run_batch_extraction
from app.extraction.memory_writer import HttpMemoryWriter, MemoryHttpConfig
from app.extraction.session_store import PostgresSessionStore
from tests.unit.extraction_fakes import FakeProvider

pytestmark = pytest.mark.iso_mcp

_POINTER = 7


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


@dataclass(frozen=True, slots=True)
class _Seed:
    org_b: UUID
    org_a: UUID
    agent_b: UUID
    session_b: UUID


async def _seed(factory: async_sessionmaker, seed: _Seed) -> None:
    async with session_as_service_account(factory) as session:
        for org_id, slug in ((seed.org_a, "iso-a"), (seed.org_b, "iso-b")):
            await session.execute(
                _sql(
                    """
                    INSERT INTO ibex_core.organizations (id, name, slug)
                    VALUES (:id, :name, :slug)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": org_id, "name": f"ISO {slug}", "slug": f"{slug}-{org_id.hex[:8]}"},
            )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug, status)
                VALUES (:id, :org_id, 'ISO Agent B', :slug, 'active')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": seed.agent_b,
                "org_id": seed.org_b,
                "slug": f"iso-agent-b-{seed.agent_b.hex[:8]}",
            },
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.sessions (
                    id, org_id, agent_id, status, model, provider, last_extracted_turn
                ) VALUES (
                    :id, :org_id, :agent_id, 'completed', 'gpt-4o-mini', 'openai', :turn
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": seed.session_b,
                "org_id": seed.org_b,
                "agent_id": seed.agent_b,
                "turn": _POINTER,
            },
        )


def _start_loop() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    loop = asyncio.new_event_loop()

    def _run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_run, name="iso-mcp-04-loop", daemon=True)
    thread.start()
    return loop, thread


def _on_loop(loop: asyncio.AbstractEventLoop, coro: object) -> object:
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=60)  # type: ignore[arg-type]


def test_iso_mcp_04_forged_org_kwargs_skip_and_no_memory_posts(
    migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forged org_id=OrgA + session_id=OrgB → session_not_found; zero memory POSTs."""
    seed = _Seed(org_b=uuid4(), org_a=uuid4(), agent_b=uuid4(), session_b=uuid4())
    loop, thread = _start_loop()
    engine: AsyncEngine | None = None
    writer: HttpMemoryWriter | None = None

    def _run_coro(coro: object) -> object:
        return _on_loop(loop, coro)

    monkeypatch.setattr(session_store_mod, "_run_coro", _run_coro)

    try:
        engine = create_engine(Settings(database_url=migrated_postgres))
        factory = create_session_factory(engine)
        _on_loop(loop, _seed(factory, seed))

        posts: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posts.append(request)
            return httpx.Response(500, json={"error": "should not be called"})

        writer = HttpMemoryWriter(
            MemoryHttpConfig(base_url="http://memory.iso.test", token="iso-token"),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        store = PostgresSessionStore(factory)
        result = run_batch_extraction(
            BatchJob(
                org_id=seed.org_a,
                agent_id=seed.agent_b,
                session_id=seed.session_b,
                turns=[
                    TurnPayload(
                        turn_index=_POINTER + 1,
                        role="user",
                        content="forged kwargs must not extract across tenants",
                    )
                ],
                provider=FakeProvider(),
                memory_writer=writer,
                clickhouse_dsn=None,
                session_store=store,
            )
        )
        snapshot = store.load(seed.org_b, seed.session_b)
    finally:
        if writer is not None:
            writer.close()
        if engine is not None:
            _on_loop(loop, engine.dispose())
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)

    assert result.skipped == "session_not_found"
    assert result.memories_written == 0
    assert posts == []
    assert snapshot is not None
    assert snapshot.last_extracted_turn == _POINTER
