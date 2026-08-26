"""HNSW recall@10 + latency benches against live pgvector (m3.2.1).

Seeds synthetic unit vectors with planted near-neighbors, then measures
PgVectorStore search latency and recall@10 at configurable corpus sizes.

Methodology gates (hard fail):
- TRUNCATE between sizes + script start; assert exact row count
- ANALYZE after COPY
- EXPLAIN must use idx_memories_embedding_hnsw; pg_stat idx_scan must move
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.vectorstore.base import SearchRequest, UpsertRequest
from app.vectorstore.pgvector_store import SEARCH_SQL, PgVectorStore

# Import plan assert relative to this file (benchmarks/memory on sys.path via argv).
import sys

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
from plan_assert import PlanAssertionError, assert_hnsw_index_used  # noqa: E402

_DIM = 1024
_DEFAULT_EF_SEARCH = 40
_DEFAULT_SIZES = (10_000, 100_000)
_QUERY_COUNTS = {10_000: 500, 100_000: 200, 1_000_000: 200}
_WARMUP_QUERIES = 100
# Larger chunks cut transaction/COPY overhead; progress prints every chunk.
_COPY_CHUNK = 20_000
_ACTIVE_DIMS = 64
_BOOTSTRAP_RESAMPLES = 1000
_HNSW_INDEX = "idx_memories_embedding_hnsw"
_HNSW_CREATE_SQL = """
CREATE INDEX idx_memories_embedding_hnsw
    ON ibex_core.memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE status = 'active' AND deleted_at IS NULL
"""


@dataclass(frozen=True, slots=True)
class SizeResult:
    corpus_size: int
    query_count: int
    recall_at_10: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_p99: float
    latency_ms_p95_ci_low: float
    latency_ms_p95_ci_high: float
    ef_search: int
    min_similarity: float
    iterative_scan: str
    index_build_mode: str
    plan_node_type: str
    plan_index_name: str
    shared_hit_blocks: int
    shared_read_blocks: int
    idx_scan_delta: int
    row_count_verified: int


def _unit_vector(seed: int) -> list[float]:
    rng = random.Random(seed)
    vec = [0.0] * _DIM
    for _ in range(_ACTIVE_DIMS):
        idx = rng.randrange(_DIM)
        vec[idx] += rng.gauss(0.0, 1.0)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _perturb(base: list[float], *, noise: float = 0.005, seed: int = 0) -> list[float]:
    rng = random.Random(seed ^ 0xA5A5_5A5A)
    out = list(base)
    for i, x in enumerate(out):
        if x != 0.0:
            out[i] = x + noise * rng.gauss(0.0, 1.0)
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6g}" for v in vec) + "]"


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    weight = rank - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def _bootstrap_p95_ci(
    samples: list[float], *, resamples: int = _BOOTSTRAP_RESAMPLES, seed: int = 42
) -> tuple[float, float]:
    if len(samples) < 2:
        p = _percentile(sorted(samples), 95)
        return p, p
    rng = random.Random(seed)
    n = len(samples)
    estimates: list[float] = []
    for _ in range(resamples):
        draw = [samples[rng.randrange(n)] for _ in range(n)]
        estimates.append(_percentile(sorted(draw), 95))
    estimates.sort()
    lo_i = int(0.025 * (len(estimates) - 1))
    hi_i = int(0.975 * (len(estimates) - 1))
    return estimates[lo_i], estimates[hi_i]


async def _exec(session: AsyncSession, sql: str, params: dict[str, object] | None = None) -> None:
    await session.execute(
        text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        params or {},
    )


async def _scalar(engine: AsyncEngine, sql: str, params: dict[str, object] | None = None) -> Any:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        result = await conn.execute(
            text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            params or {},
        )
        return result.scalar()


async def _reset_memories(engine: AsyncEngine) -> None:
    """TRUNCATE memories (+ dependent label/relationship rows) for a clean corpus."""
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.memories CASCADE"
            )
        )


async def _analyze_memories(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "ANALYZE ibex_core.memories"
            )
        )


async def _count_memories(engine: AsyncEngine) -> int:
    value = await _scalar(engine, "SELECT count(*)::bigint FROM ibex_core.memories")
    return int(value or 0)


async def _idx_scan_count(engine: AsyncEngine) -> int:
    # PG15+ buffers stats; flush so deltas are visible to this process.
    await _scalar(engine, "SELECT pg_stat_force_next_flush()")
    value = await _scalar(
        engine,
        """
        SELECT coalesce(sum(idx_scan), 0)::bigint
        FROM pg_stat_all_indexes
        WHERE indexrelname = :name
        """,
        {"name": _HNSW_INDEX},
    )
    return int(value or 0)


async def _ensure_hnsw_index(engine: AsyncEngine) -> None:
    exists = await _scalar(
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
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        # Bound parallel index build memory so CREATE INDEX fits container shm.
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('maintenance_work_mem', '1GB', true)"
            )
        )
        await conn.execute(
            text(_HNSW_CREATE_SQL)  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        )


async def _drop_hnsw_index(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "DROP INDEX IF EXISTS ibex_core.idx_memories_embedding_hnsw"
            )
        )


async def _try_prewarm(engine: AsyncEngine) -> bool:
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


async def _seed_org(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    org_id, user_id, agent_id = uuid4(), uuid4(), uuid4()
    slug = f"bench-{org_id.hex[:8]}"
    async with factory() as session, session.begin():
        await _exec(session, "SELECT set_config('app.is_service_account', 'true', true)")
        await _exec(
            session,
            """
            INSERT INTO ibex_core.organizations (id, name, slug)
            VALUES (:id, :name, :slug)
            """,
            {"id": str(org_id), "name": f"Bench {slug}", "slug": slug},
        )
        await _exec(
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
        await _exec(
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


def _memory_id_for(org_id: UUID, idx: int) -> UUID:
    return uuid5(org_id, f"bench-{idx}")


async def _bulk_insert_memories(
    engine: AsyncEngine,
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
) -> None:
    """Seed via asyncpg text/CSV COPY in chunks (pgvector has no binary encoder)."""
    import csv
    from io import BytesIO, StringIO

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
            mid = _memory_id_for(org_id, idx)
            writer.writerow(
                [
                    str(mid),
                    str(org_id),
                    str(agent_id),
                    f"bench-{mid.hex}",
                    f"h-{mid.hex}",
                    1,
                    _vec_literal(_unit_vector(idx)),
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
                    "SELECT set_config('app.is_service_account', 'true', true)"
                )
            )
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('app.current_org_id', :org_id, true)"
                ),
                {"org_id": str(org_id)},
            )
            # Bench-only: skip fsync wait on ephemeral test DB (huge COPY speedup).
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('synchronous_commit', 'off', true)"
                )
            )
            raw = await conn.get_raw_connection()
            driver = raw.driver_connection
            assert driver is not None
            await driver.copy_to_table(
                "memories",
                source=payload,
                columns=columns,
                schema_name="ibex_core",
                format="csv",
            )
        print(f"  seeded {end}/{total}", flush=True)


async def _explain_search(
    engine: AsyncEngine,
    *,
    org_id: UUID,
    agent_id: UUID,
    query: list[float],
    ef_search: int,
    min_similarity: float,
    iterative_scan: str,
    limit: int = 10,
) -> dict[str, Any]:
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {SEARCH_SQL}"
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
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
                "SELECT set_config('hnsw.ef_search', :ef, true)"
            ),
            {"ef": str(ef_search)},
        )
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('hnsw.iterative_scan', :mode, true)"
            ),
            {"mode": iterative_scan},
        )
        result = await conn.execute(
            text(explain_sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {
                "query": _vec_literal(query),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "min_similarity": min_similarity,
                "limit": limit,
            },
        )
        payload = result.scalar()
    if isinstance(payload, str):
        payload = json.loads(payload)
    summary = assert_hnsw_index_used(payload)
    print(
        f"  EXPLAIN ok node={summary['node_type']} index={summary['index_name']} "
        f"hits={summary['shared_hit_blocks']} reads={summary['shared_read_blocks']} "
        f"exec_ms={summary.get('execution_time_ms')}",
        flush=True,
    )
    return summary


async def _run_size(
    store: PgVectorStore,
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
    query_count: int,
    ef_search: int,
    min_similarity: float,
    iterative_scan: str,
    index_build_mode: str,
    plan_summary: dict[str, Any],
    idx_scan_delta: int,
    row_count: int,
) -> SizeResult:
    # Warm-up (discarded).
    for q in range(_WARMUP_QUERIES):
        idx = (q * 97) % size
        await store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=_perturb(_unit_vector(idx), seed=idx),
                limit=10,
                min_similarity=min_similarity,
                ef_search=ef_search,
                iterative_scan=iterative_scan,
            )
        )

    latencies: list[float] = []
    hits = 0
    for q in range(query_count):
        idx = (q * 97) % size
        query = _perturb(_unit_vector(idx), seed=idx)
        t0 = time.perf_counter()
        results = await store.search(
            SearchRequest(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=query,
                limit=10,
                min_similarity=min_similarity,
                ef_search=ef_search,
                iterative_scan=iterative_scan,
            )
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
        top_ids = {hit.memory_id for hit in results}
        if _memory_id_for(org_id, idx) in top_ids:
            hits += 1

    ordered = sorted(latencies)
    ci_lo, ci_hi = _bootstrap_p95_ci(latencies)
    return SizeResult(
        corpus_size=size,
        query_count=query_count,
        recall_at_10=hits / query_count,
        latency_ms_p50=_percentile(ordered, 50),
        latency_ms_p95=_percentile(ordered, 95),
        latency_ms_p99=_percentile(ordered, 99),
        latency_ms_p95_ci_low=ci_lo,
        latency_ms_p95_ci_high=ci_hi,
        ef_search=ef_search,
        min_similarity=min_similarity,
        iterative_scan=iterative_scan,
        index_build_mode=index_build_mode,
        plan_node_type=str(plan_summary.get("node_type") or ""),
        plan_index_name=str(plan_summary.get("index_name") or ""),
        shared_hit_blocks=int(plan_summary.get("shared_hit_blocks") or 0),
        shared_read_blocks=int(plan_summary.get("shared_read_blocks") or 0),
        idx_scan_delta=idx_scan_delta,
        row_count_verified=row_count,
    )


async def _prepare_corpus(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    *,
    size: int,
    index_build_mode: str,
) -> tuple[UUID, UUID, float]:
    await _reset_memories(engine)
    if index_build_mode == "bulk":
        await _drop_hnsw_index(engine)
    else:
        await _ensure_hnsw_index(engine)

    org_id, agent_id = await _seed_org(factory)
    print(f"seeding corpus_size={size} mode={index_build_mode} …", flush=True)
    t0 = time.perf_counter()
    await _bulk_insert_memories(engine, org_id=org_id, agent_id=agent_id, size=size)
    if index_build_mode == "bulk":
        print("  CREATE INDEX (bulk) …", flush=True)
        await _ensure_hnsw_index(engine)
    build_s = time.perf_counter() - t0
    await _analyze_memories(engine)
    count = await _count_memories(engine)
    if count != size:
        msg = f"row count after seed expected {size}, got {count}"
        raise RuntimeError(msg)
    print(f"  row_count={count} build_s={build_s:.2f} ANALYZE ok", flush=True)
    return org_id, agent_id, build_s


async def _measure_cell(
    engine: AsyncEngine,
    store: PgVectorStore,
    *,
    org_id: UUID,
    agent_id: UUID,
    size: int,
    ef_search: int,
    min_similarity: float,
    iterative_scan: str,
    index_build_mode: str,
    query_count: int | None,
    row_count: int,
    prewarm: bool,
) -> SizeResult:
    """Time one (min_similarity × iterative_scan) cell on an already-seeded corpus."""
    plan_summary = await _explain_search(
        engine,
        org_id=org_id,
        agent_id=agent_id,
        query=_unit_vector(0),
        ef_search=ef_search,
        min_similarity=min_similarity,
        iterative_scan=iterative_scan,
    )
    if prewarm:
        await _try_prewarm(engine)

    qn = query_count if query_count is not None else _QUERY_COUNTS.get(size, 200)
    before = await _idx_scan_count(engine)
    print(
        f"searching size={size} ef={ef_search} min_sim={min_similarity} "
        f"iter={iterative_scan} queries={qn} warmup={_WARMUP_QUERIES} …",
        flush=True,
    )
    result = await _run_size(
        store,
        org_id=org_id,
        agent_id=agent_id,
        size=size,
        query_count=qn,
        ef_search=ef_search,
        min_similarity=min_similarity,
        iterative_scan=iterative_scan,
        index_build_mode=index_build_mode,
        plan_summary=plan_summary,
        idx_scan_delta=0,
        row_count=row_count,
    )
    after = await _idx_scan_count(engine)
    delta = after - before
    if delta < 1:
        msg = (
            f"pg_stat_user_indexes idx_scan did not increase "
            f"(before={before}, after={after}) — HNSW index not used"
        )
        raise PlanAssertionError(msg)
    result = SizeResult(**{**asdict(result), "idx_scan_delta": delta})
    print(
        f"size={size} recall@10={result.recall_at_10:.4f} "
        f"p95_ms={result.latency_ms_p95:.2f} "
        f"p95_ci=[{result.latency_ms_p95_ci_low:.2f},{result.latency_ms_p95_ci_high:.2f}] "
        f"idx_scan_delta={delta}",
        flush=True,
    )
    return result


async def _benchmark(args: argparse.Namespace) -> dict[str, object]:
    dsn = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not dsn:
        msg = "IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required"
        raise RuntimeError(msg)

    settings = Settings(database_url=dsn, hnsw_ef_search=args.ef_search)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = PgVectorStore(factory, settings)

    sizes = list(args.sizes)
    iterative_modes = list(args.iterative_scan)
    min_sims = list(args.min_similarity)
    index_modes = list(args.index_build_mode)

    results: list[SizeResult] = []
    try:
        await _reset_memories(engine)
        await _ensure_hnsw_index(engine)
        for size in sizes:
            for index_build_mode in index_modes:
                # Seed once per (size × build mode). Search knobs share the corpus —
                # re-seeding 4× was the main local wall-clock cost.
                org_id, agent_id, _build_s = await _prepare_corpus(
                    engine, factory, size=size, index_build_mode=index_build_mode
                )
                await store.upsert(
                    UpsertRequest(
                        memory_id=_memory_id_for(org_id, 0),
                        org_id=org_id,
                        embedding=_unit_vector(0),
                        embedding_model="bench-synthetic",
                    )
                )
                count = await _count_memories(engine)
                if count != size:
                    msg = f"row count after upsert expected {size}, got {count}"
                    raise RuntimeError(msg)

                first_cell = True
                for iterative_scan in iterative_modes:
                    for min_similarity in min_sims:
                        cell = await _measure_cell(
                            engine,
                            store,
                            org_id=org_id,
                            agent_id=agent_id,
                            size=size,
                            ef_search=args.ef_search,
                            min_similarity=min_similarity,
                            iterative_scan=iterative_scan,
                            index_build_mode=index_build_mode,
                            query_count=args.queries,
                            row_count=count,
                            prewarm=first_cell,
                        )
                        results.append(cell)
                        first_cell = False
    finally:
        await engine.dispose()

    payload: dict[str, object] = {
        "benchmark": "hnsw_recall_latency",
        "generated_at": datetime.now(UTC).isoformat(),
        "methodology": {
            "index": "idx_memories_embedding_hnsw (m=16, ef_construction=64, cosine)",
            "ef_search": args.ef_search,
            "dim": _DIM,
            "active_dims": _ACTIVE_DIMS,
            "warmup_queries": _WARMUP_QUERIES,
            "truncate_between_sizes": True,
            "reuse_corpus_across_search_knobs": True,
            "analyze_after_copy": True,
            "explain_requires_hnsw": True,
            "recall": "planted near-neighbor must appear in top-10",
            "latency": "wall-clock PgVectorStore.search including SET LOCAL",
            "iterative_scan_modes": iterative_modes,
            "min_similarity_values": min_sims,
            "index_build_modes": index_modes,
        },
        "results": [asdict(r) for r in results],
        "mean_recall_at_10": statistics.fmean(r.recall_at_10 for r in results)
        if results
        else 0.0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=list(_DEFAULT_SIZES),
        help="Corpus sizes (default: 10K 100K; avoid 1M on laptop)",
    )
    parser.add_argument(
        "--ef-search",
        type=int,
        default=_DEFAULT_EF_SEARCH,
        help="hnsw.ef_search (default: 40 — roadmap SLA)",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        nargs="+",
        default=[0.0, 0.70],
        help="SearchRequest min_similarity values to matrix (default: 0.0 0.70)",
    )
    parser.add_argument(
        "--iterative-scan",
        type=str,
        nargs="+",
        default=["off", "relaxed_order"],
        choices=["off", "relaxed_order", "strict_order"],
        help="hnsw.iterative_scan modes to matrix",
    )
    parser.add_argument(
        "--index-build-mode",
        type=str,
        nargs="+",
        default=["incremental"],
        choices=["incremental", "bulk"],
        help="incremental = COPY into existing HNSW; bulk = COPY then CREATE INDEX",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=None,
        help="Override timed query count for all sizes",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_BENCH_DIR / "output" / "hnsw_recall_latency.json",
    )
    args = parser.parse_args()
    if args.ef_search < 1:
        parser.error("--ef-search must be >= 1")
    asyncio.run(_benchmark(args))


if __name__ == "__main__":
    main()
