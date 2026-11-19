"""Shared harness for the memory-lifecycle erasure integration suite.

Why the suite is split: the consumer has two families of behaviour that fail for
different reasons. ``test_memory_lifecycle_erasure_postgres.py`` covers the paths
where every store can be proven, and
``test_memory_lifecycle_erasure_retry_postgres.py`` covers the paths where a
store cannot be — the unreachable store, the superseded revision, the refused
cross-tenant locator. The ClickHouse helper, the object-store stub, the seeding
helpers and the read-back helpers are shared from here so the two modules cannot
drift apart; the fixtures that wire them to pytest live in ``conftest.py``.

What is real and what is not:

* PostgreSQL is real. Every consumer statement runs through
  ``session_as_app_org`` (``ibex_app`` plus the org GUC), so the RLS policies and
  the tenant grants production uses are the ones exercised here, and the claim
  runs through the ``SECURITY DEFINER`` function as the ``ibex_worker`` login.
* ClickHouse is real: the evidence event is inserted through the HTTP interface
  and its absence is read back after the mutation.
* The object store is the one stub — this suite has no MinIO — so
  ``delete_uri``/``object_exists`` are replaced by a fake that records calls and
  can report an object still present. The unreachable-store case does **not** use
  the fake: it configures no ClickHouse DSN, which is the real "deployed but
  unreachable" condition and must never produce ``verified``.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import redis as redis_sync
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.extraction.clickhouse_traces import _http_endpoint
from app.tasks import lifecycle_erasure
from tests.integration.tenant_pinning_support import (
    SessionEventSeed,
    SessionSeed,
    count_rows,
    fetch_all,
    fetch_one,
    seed_org,
    seed_session,
    seed_session_event,
    seed_tenant_rows,
    sql_text,
)

#: ClickHouse HTTP DSN the suite probes; a run without ClickHouse skips.
CH_DSN = os.environ.get(
    "CLICKHOUSE_TEST_HTTP_DSN", "http://default:ibextest@127.0.0.1:8124/"
)

_CH_INSERT = (
    "INSERT INTO ibex.evidence_events (org_id, event_id, aggregate_id, aggregate_seq,"
    " schema_version, event_type, redaction_class, resource_type, resource_id,"
    " resource_version, payload, received_at) FORMAT JSONEachRow"
)

# Literal cleanup statements keyed by nothing: the tables are constants, so no
# identifier is ever built from a value (Bandit B608).
CLEANUP_STATEMENTS: tuple[str, ...] = (
    "DELETE FROM ibex_core.memory_lifecycle_outbox",
    "DELETE FROM ibex_core.erasure_store_receipts",
    "DELETE FROM ibex_core.memory_artifact_refs",
)

_MEMORY_INSERT_SQL = """
INSERT INTO ibex_core.memories
    (id, org_id, agent_id, content, content_hash, content_tokens)
VALUES (:id, :org, :agent, 'forgotten fixture', :hash, 3)
"""

_REF_INSERT_SQL = """
INSERT INTO ibex_core.memory_artifact_refs
    (org_id, memory_id, store, locator, session_id)
VALUES (:org, :memory, :store, :locator, :session)
"""

_OUTBOX_INSERT_SQL = """
INSERT INTO ibex_core.memory_lifecycle_outbox
    (org_id, memory_id, revision, event_type, delivered_at, erasure_state)
VALUES (:org, :memory, :revision, :event_type,
        CASE WHEN :delivered THEN NOW() ELSE NULL END,
        COALESCE(CAST(:state AS text), 'pending'))
RETURNING id::text
"""


# ---------------------------------------------------------------------------
# ClickHouse (real store)
# ---------------------------------------------------------------------------


def require_clickhouse(dsn: str) -> str:
    """Return ``dsn``, skipping the suite when ClickHouse is not reachable."""
    url, auth = _http_endpoint(dsn)
    try:
        resp = httpx.post(url, params={"query": "SELECT 1"}, auth=auth, timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"ClickHouse not available at {url}: {exc}")
    if resp.status_code >= 400:
        pytest.skip(f"ClickHouse rejected a probe at {url}: {resp.status_code}")
    return dsn


def seed_clickhouse_event(dsn: str, *, org_id: UUID, event_id: UUID) -> None:
    """Insert one evidence event the way a producer would."""
    url, auth = _http_endpoint(dsn)
    row = {
        "org_id": str(org_id),
        "event_id": str(event_id),
        "aggregate_id": str(event_id),
        "aggregate_seq": 1,
        "schema_version": "v1",
        "event_type": "capture",
        "redaction_class": "internal",
        "resource_type": "memory",
        "resource_id": str(event_id),
        "resource_version": 1,
        "payload": "{}",
        "received_at": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    }
    resp = httpx.post(
        url,
        params={"query": _CH_INSERT},
        content=json.dumps(row),
        auth=auth,
        timeout=10.0,
    )
    assert resp.status_code < 400, resp.text


def clickhouse_event_count(dsn: str, *, org_id: UUID, event_id: UUID) -> int:
    """How many rows the evidence event still has in ClickHouse."""
    url, auth = _http_endpoint(dsn)
    # Literal query, UUIDs from uuid4: no caller input reaches this string.
    query = (
        "SELECT count() FROM ibex.evidence_events"
        f" WHERE org_id = '{org_id}' AND event_id = '{event_id}'"
    )
    resp = httpx.post(url, params={"query": query}, auth=auth, timeout=10.0)
    assert resp.status_code < 400, resp.text
    return int(resp.text.strip() or "0")


# ---------------------------------------------------------------------------
# Object-store stub (no MinIO in this suite)
# ---------------------------------------------------------------------------


@dataclass
class FakeObjectStore:
    """Records deletes and reports what is still present.

    ``present`` is the set of URIs the store still holds; ``delete`` removes from
    it so ``object_exists`` can prove absence the way HEAD does. ``raises`` makes
    every call fail, which is how the "store answers with an error" path is
    exercised without inventing a receipt status. ``slow_calls`` makes that many
    HEADs take ``delay`` seconds each, which is how a slow store spends a budget
    the caller must cap without making every later check slow too.
    """

    present: set[str] = field(default_factory=set)
    deleted: list[str] = field(default_factory=list)
    raises: bool = False
    delay: float = 0.0
    slow_calls: int = 0

    def delete(self, uri: str, *, org_id: str, settings: Any | None = None) -> None:
        del org_id, settings
        if self.raises:
            raise RuntimeError("s3 delete capture/1.json: 503")
        self.deleted.append(uri)
        self.present.discard(uri)

    def exists(self, uri: str, *, org_id: str, settings: Any | None = None) -> bool:
        del org_id, settings
        if self.slow_calls > 0:
            self.slow_calls -= 1
            time.sleep(self.delay)
        if self.raises:
            raise RuntimeError("s3 head capture/1.json: 503")
        return uri in self.present


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Forgotten:
    """One forgotten memory with the copies a forget has to erase."""

    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    session_event_id: int
    ch_event_id: UUID
    object_uri: str
    object_cache_key: str
    hot_cache_key: str


@dataclass(frozen=True, slots=True)
class RefSeed:
    """The artifact refs one memory is given."""

    org_id: UUID
    memory_id: UUID
    session_id: UUID | None
    locators: dict[str, str]


@dataclass(frozen=True, slots=True)
class OutboxSeed:
    """One memory_lifecycle_outbox row; the defaults match a fresh forget."""

    org_id: UUID
    memory_id: UUID
    revision: int = 2
    event_type: str = "forgotten"
    delivered: bool = False
    erasure_state: str | None = None

    @classmethod
    def for_memory(cls, forgotten: Forgotten, **overrides: Any) -> OutboxSeed:
        """The row a forget of ``forgotten`` writes, with any field overridden."""
        base = cls(org_id=forgotten.org_id, memory_id=forgotten.memory_id)
        return replace(base, **overrides)


async def insert_memory(
    owner: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
) -> None:
    """Seed the memory row the forget tombstoned."""
    async with owner() as session, session.begin():
        await session.execute(
            sql_text(_MEMORY_INSERT_SQL),
            {
                "id": memory_id,
                "org": org_id,
                "agent": agent_id,
                "hash": f"h-{memory_id}",
            },
        )


def _ref_params(seed: RefSeed, store: str, locator: str) -> dict[str, Any]:
    return {
        "org": seed.org_id,
        "memory": seed.memory_id,
        "store": store,
        "locator": locator,
        "session": seed.session_id,
    }


async def insert_refs(owner: async_sessionmaker[AsyncSession], seed: RefSeed) -> None:
    """Seed the artifact refs a producer would have recorded."""
    async with owner() as session, session.begin():
        for store, locator in seed.locators.items():
            await session.execute(
                sql_text(_REF_INSERT_SQL), _ref_params(seed, store, locator)
            )


def _outbox_params(seed: OutboxSeed) -> dict[str, Any]:
    return {
        "org": seed.org_id,
        "memory": seed.memory_id,
        "revision": seed.revision,
        "event_type": seed.event_type,
        "delivered": seed.delivered,
        "state": seed.erasure_state,
    }


async def insert_outbox(
    owner: async_sessionmaker[AsyncSession], seed: OutboxSeed
) -> str:
    """Insert one lifecycle outbox row and return its id."""
    async with owner() as session, session.begin():
        row = (
            await session.execute(sql_text(_OUTBOX_INSERT_SQL), _outbox_params(seed))
        ).one()
    return str(row[0])


async def read_receipts(
    owner: async_sessionmaker[AsyncSession], *, org_id: UUID, memory_id: UUID
) -> dict[str, tuple[str, str | None, datetime | None]]:
    """Every receipt of one memory, keyed by store."""
    rows = await fetch_all(
        owner,
        """
        SELECT store, status, error, verified_absent_at
          FROM ibex_core.erasure_store_receipts
         WHERE org_id = :org AND memory_id = :memory
         ORDER BY store
        """,
        org=org_id,
        memory=memory_id,
    )
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


async def read_outbox(
    owner: async_sessionmaker[AsyncSession], *, row_id: str
) -> tuple[str, datetime | None, datetime | None, int]:
    """The state, delivery, next-attempt and attempt count of one outbox row."""
    row = await fetch_one(
        owner,
        """
        SELECT erasure_state, delivered_at, available_at, attempts
          FROM ibex_core.memory_lifecycle_outbox
         WHERE id = CAST(:id AS uuid)
        """,
        id=row_id,
    )
    return row[0], row[1], row[2], int(row[3])


def seed_cache_copies(
    redis_url: str, *, org_id: UUID, agent_id: UUID, memory_id: UUID
) -> tuple[str, str]:
    """Write both cached copies a memory write produces; return their keys.

    The object entry carries content — it is the disclosure a failed eviction
    would leave readable. The hot set carries the memory id and a score, and the
    erasure must remove the member, not the key, so the fixture seeds a second
    live member that must survive.
    """
    object_key = f"{org_id}:memory:{memory_id}"
    hot_key = f"{org_id}:hot_memories:{agent_id}"
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        client.set(object_key, json.dumps({"id": str(memory_id), "content": "cached"}))
        client.zadd(hot_key, {str(memory_id): 1.0, "live-other-memory": 0.5})
    finally:
        client.close()
    return object_key, hot_key


def cache_key_exists(redis_url: str, key: str) -> bool:
    """Whether the object cache entry is still present."""
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        return bool(client.exists(key))
    finally:
        client.close()


def cache_member_scored(redis_url: str, key: str, member: str) -> bool:
    """Whether the hot sorted set still scores this memory id."""
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        return client.zscore(key, member) is not None
    finally:
        client.close()


def add_hot_member(redis_url: str, key: str, member: str) -> None:
    """Write the hot member the way a delayed ``refresh_hot`` would land it.

    This is the unguarded ZADD the memory service performs *after* its own
    forgotten-marker check. The race tests use it to place a member at a chosen
    instant; the fence test drives the guarded script instead.
    """
    client = redis_sync.Redis.from_url(redis_url, decode_responses=True)
    try:
        client.zadd(key, {member: 1.0})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErasureEnv:
    """The real dependencies one consumer run needs."""

    owner: async_sessionmaker[AsyncSession]
    dsn: str
    redis_url: str
    ch_dsn: str


@dataclass(frozen=True, slots=True)
class Harness:
    """Seed a forgotten memory, run the consumer, and read the result back."""

    env: ErasureEnv

    def settings(
        self, *, ch_dsn: str | None, redis_url: str | None = None
    ) -> Settings:
        """Consumer settings for one run.

        ``ch_dsn=None`` means ClickHouse is deployed but unreachable;
        ``redis_url`` overrides the cache endpoint so a test can make Redis
        unreachable without touching the real one.
        """
        return Settings(
            database_url=self.env.dsn,
            redis_url=redis_url or self.env.redis_url,
            clickhouse_dsn=ch_dsn,
            s3_endpoint="https://objectstore.invalid",
            lifecycle_erasure_job_timeout_seconds=60.0,
            lifecycle_erasure_store_timeout_seconds=20.0,
        )

    async def run(
        self, *, ch_dsn: str | None, redis_url: str | None = None
    ) -> dict[str, Any]:
        """One sweep, with the batch size the suite standardises on."""
        settings = self.settings(ch_dsn=ch_dsn, redis_url=redis_url)
        return await lifecycle_erasure._run_sweep(settings=settings, claim_batch=5)

    @asynccontextmanager
    async def factory(self, *, ch_dsn: str | None) -> AsyncIterator[Any]:
        """A session factory for the consumer's own helpers, disposed on exit."""
        engine = lifecycle_erasure.create_engine(self.settings(ch_dsn=ch_dsn))
        try:
            yield lifecycle_erasure.create_session_factory(engine)
        finally:
            await engine.dispose()

    async def seed(self, *, with_refs: bool = True) -> Forgotten:
        """Seed org, agent, session, memory, one session event, and the refs."""
        owner = self.env.owner
        org_id = uuid4()
        await seed_org(owner, org_id)
        _, agent_id = await seed_tenant_rows(owner, org_id, tag=org_id.hex[:8])
        session_id = uuid4()
        await seed_session(
            owner,
            SessionSeed(org_id=org_id, agent_id=agent_id, session_id=session_id),
        )
        memory_id, ch_event_id = uuid4(), uuid4()
        object_uri = f"s3://ibex-sessions/{org_id}/capture/full/{ch_event_id}.json"
        await insert_memory(
            owner, org_id=org_id, agent_id=agent_id, memory_id=memory_id
        )
        object_cache_key = hot_cache_key = ""
        if with_refs:
            object_cache_key, hot_cache_key = seed_cache_copies(
                self.env.redis_url,
                org_id=org_id,
                agent_id=agent_id,
                memory_id=memory_id,
            )
        event_id = await seed_session_event(
            owner,
            SessionEventSeed(
                org_id=org_id,
                session_id=session_id,
                data={"memory_ids": [str(memory_id)]},
            ),
        )
        forgotten = Forgotten(
            org_id=org_id,
            agent_id=agent_id,
            memory_id=memory_id,
            session_event_id=event_id,
            ch_event_id=ch_event_id,
            object_uri=object_uri,
            object_cache_key=object_cache_key,
            hot_cache_key=hot_cache_key,
        )
        if with_refs:
            seed_clickhouse_event(
                self.env.ch_dsn, org_id=org_id, event_id=ch_event_id
            )
            await self.refs(
                RefSeed(
                    org_id=org_id,
                    memory_id=memory_id,
                    session_id=session_id,
                    locators={
                        "objectstore": object_uri,
                        "clickhouse": str(ch_event_id),
                        "session_event": str(event_id),
                        "cache": object_cache_key,
                        "cache_hot": hot_cache_key,
                    },
                )
            )
        return forgotten

    async def refs(self, seed: RefSeed) -> None:
        """Give one memory the artifact refs a producer would have recorded."""
        await insert_refs(self.env.owner, seed)

    async def seed_queued(self, store: FakeObjectStore) -> tuple[Forgotten, str]:
        """Seed a forgotten memory, queue its erasure, and hold its object.

        Returns the seeded memory and the outbox row id, which is what every
        end-to-end case in the suite needs before it runs a sweep.
        """
        forgotten = await self.seed()
        row_id = await self.queue(OutboxSeed.for_memory(forgotten))
        store.present.add(forgotten.object_uri)
        return forgotten, row_id

    async def queue(self, seed: OutboxSeed) -> str:
        """Write the outbox row a forget would write; return its id."""
        return await insert_outbox(self.env.owner, seed)

    async def seed_receipt(
        self,
        forgotten: Forgotten,
        *,
        store: str,
        status: str = "verified",
        revision: int = 2,
    ) -> None:
        """Record the receipt an earlier run of this revision would have written.

        A test that needs the durable-proof path (rather than a fresh stage) has
        to start from a proof, and the consumer never rewrites a verified
        receipt, so the row has to be seeded exactly as a previous run left it.
        """
        idem = f"erase:{forgotten.org_id}:{forgotten.memory_id}:{revision}:{store}"
        async with self.env.owner() as session, session.begin():
            await session.execute(
                sql_text(
                    """
                    INSERT INTO ibex_core.erasure_store_receipts (
                        org_id, memory_id, revision, store, status,
                        verified_absent_at, idempotency_key
                    ) VALUES (
                        :org, :memory, :revision, :store, :status,
                        CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
                        :idem
                    )
                    """
                ),
                {
                    "org": forgotten.org_id,
                    "memory": forgotten.memory_id,
                    "revision": revision,
                    "store": store,
                    "status": status,
                    "idem": idem,
                },
            )

    async def receipts(
        self, *, org_id: UUID, memory_id: UUID
    ) -> dict[str, tuple[str, str | None, datetime | None]]:
        return await read_receipts(self.env.owner, org_id=org_id, memory_id=memory_id)

    async def artifact_refs(self, forgotten: Forgotten) -> dict[str, tuple[str, ...]]:
        """The artifact addresses recorded for one memory, grouped by store."""
        rows = await fetch_all(
            self.env.owner,
            """
            SELECT store, locator
              FROM ibex_core.memory_artifact_refs
             WHERE org_id = :org AND memory_id = :memory
             ORDER BY store, locator
            """,
            org=forgotten.org_id,
            memory=forgotten.memory_id,
        )
        grouped: dict[str, list[str]] = {}
        for store, locator in rows:
            grouped.setdefault(str(store), []).append(str(locator))
        return {store: tuple(locators) for store, locators in grouped.items()}

    async def outbox(
        self, *, row_id: str
    ) -> tuple[str, datetime | None, datetime | None, int]:
        return await read_outbox(self.env.owner, row_id=row_id)

    async def make_due(self, row_id: str) -> None:
        """Fast-forward a row's backoff instead of sleeping out the retry delay."""
        async with self.env.owner() as session, session.begin():
            await session.execute(
                sql_text(
                    "UPDATE ibex_core.memory_lifecycle_outbox"
                    " SET available_at = NOW() - interval '1 second'"
                    " WHERE id = CAST(:id AS uuid)"
                ),
                {"id": row_id},
            )

    def clickhouse_count(self, forgotten: Forgotten) -> int:
        """How many copies of this memory's evidence event ClickHouse still has."""
        return clickhouse_event_count(
            self.env.ch_dsn,
            org_id=forgotten.org_id,
            event_id=forgotten.ch_event_id,
        )

    async def session_event_count(self, forgotten: Forgotten) -> int:
        """How many copies of this memory's capture event still exist."""
        return await count_rows(
            self.env.owner,
            "SELECT count(*) FROM ibex_core.session_events"
            " WHERE id = :id AND org_id = :org",
            id=forgotten.session_event_id,
            org=forgotten.org_id,
        )

    def cached_object_present(self, forgotten: Forgotten) -> bool:
        """Whether the content-bearing object cache entry still exists."""
        return cache_key_exists(self.env.redis_url, forgotten.object_cache_key)

    def hot_member_present(self, forgotten: Forgotten) -> bool:
        """Whether the hot sorted set still scores this memory id."""
        return cache_member_scored(
            self.env.redis_url, forgotten.hot_cache_key, str(forgotten.memory_id)
        )

    def add_hot_member(self, forgotten: Forgotten) -> None:
        """Land the delayed write that recreates this memory's hot member."""
        add_hot_member(
            self.env.redis_url, forgotten.hot_cache_key, str(forgotten.memory_id)
        )

    def forgotten_marker_key(self, forgotten: Forgotten) -> str:
        """The per-memory marker the memory service checks before a hot write."""
        namespace = lifecycle_erasure._CACHE_FORGOTTEN_NAMESPACE
        return f"{forgotten.org_id}:{namespace}:{forgotten.memory_id}"

    def forgotten_marker_present(self, forgotten: Forgotten) -> bool:
        """Whether the marker that fences a delayed hot write has been written."""
        return cache_key_exists(
            self.env.redis_url, self.forgotten_marker_key(forgotten)
        )

    def hot_other_member_present(self, forgotten: Forgotten) -> bool:
        """Whether the fixture's second, live member survived the purge."""
        return cache_member_scored(
            self.env.redis_url, forgotten.hot_cache_key, "live-other-memory"
        )

    async def receipt_row_count(self, forgotten: Forgotten, store: str) -> int:
        """How many receipt rows exist for one store (the unique key allows one)."""
        return await count_rows(
            self.env.owner,
            "SELECT count(*) FROM ibex_core.erasure_store_receipts"
            " WHERE org_id = :org AND memory_id = :memory AND store = :store",
            org=forgotten.org_id,
            memory=forgotten.memory_id,
            store=store,
        )

    async def artifact_ref_count(self, forgotten: Forgotten) -> int:
        """How many artifact refs the memory still has (they outlive erasure)."""
        return await count_rows(
            self.env.owner,
            "SELECT count(*) FROM ibex_core.memory_artifact_refs"
            " WHERE org_id = :org AND memory_id = :memory",
            org=forgotten.org_id,
            memory=forgotten.memory_id,
        )
