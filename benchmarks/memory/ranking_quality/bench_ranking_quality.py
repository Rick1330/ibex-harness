#!/usr/bin/env python3
"""Ranking-quality benchmark — gold set via MemoryReadRepository.find_similar."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_BENCH_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_DIR = _BENCH_ROOT / "services" / "memory"
_BENCH_MEMORY = _BENCH_ROOT / "benchmarks" / "memory"
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))

from app.config import Settings  # noqa: E402
from app.db import create_engine, create_session_factory  # noqa: E402
from app.read.models import FindSimilarQuery  # noqa: E402
from app.read.repository import MemoryReadRepository  # noqa: E402
from app.vectorstore.pgvector_store import PgVectorStore  # noqa: E402
from path_guard import resolve_bench_input_path, write_bench_output_json  # noqa: E402
from tests.integration.conftest import zero_embedding  # noqa: E402

_RANK_DIR = Path(__file__).resolve().parent
if str(_RANK_DIR) not in sys.path:
    sys.path.insert(0, str(_RANK_DIR))

from metrics import (  # noqa: E402
    expected_order_match,
    macro_mean,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from seed import GOLD_SET_PATH, load_gold_set, seed_gold_set  # noqa: E402
from validate_gold_set import validate_gold_set  # noqa: E402

DEFAULT_OUTPUT = _RANK_DIR / "output" / "latest.json"


def _async_dsn() -> str:
    raw = (
        os.getenv("IBEX_MEMORY_DATABASE_URL")
        or os.getenv("POSTGRES_TEST_DSN")
        or os.getenv("POSTGRES_DSN")
    )
    if not raw:
        msg = "IBEX_MEMORY_DATABASE_URL or POSTGRES_TEST_DSN required"
        raise RuntimeError(msg)
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


async def run_bench(*, gold_path: Path) -> dict:
    settings = Settings(database_url=_async_dsn()).model_copy(
        update={"search_fallback_enabled": False},
    )
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    store = PgVectorStore(session_factory, settings)
    repo = MemoryReadRepository(session_factory, store, settings)

    seed = await seed_gold_set(session_factory, store, gold_path=gold_path)
    id_to_key = {str(v): k for k, v in seed.content_key_to_memory_id.items()}
    payload = load_gold_set(gold_path)
    errors = validate_gold_set(payload)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(f"gold set validation failed:\n{joined}")
    queries = payload["queries"]
    mem_by_key = {m["content_key"]: m for m in payload["memories"]}

    per_query: list[dict] = []
    p5_vals: list[float] = []
    r10_vals: list[float] = []
    mrr_vals: list[float] = []
    order_vals: list[float] = []
    top_cat_hits = 0

    for row in queries:
        query_id = str(row["query_id"])
        hotspot = int(row["query_hotspot"])
        expected_keys = list(row["expected_content_keys"])
        expected_top = str(row.get("expected_top_category", ""))
        query_vec = zero_embedding(hotspot=hotspot)

        results = await repo.find_similar(
            FindSimilarQuery(
                org_id=seed.org_id,
                agent_id=seed.agent_id,
                query_embedding=query_vec,
                query_text=str(row["query_text"]),
                limit=10,
                min_similarity=0.5,
            )
        )
        ranked_keys = [
            id_to_key[str(hit.id)]
            for hit in results
            if str(hit.id) in id_to_key
        ]
        p5 = precision_at_k(ranked_keys, expected_keys, 5)
        r10 = recall_at_k(ranked_keys, expected_keys, 10)
        mrr = mean_reciprocal_rank(ranked_keys, expected_keys)
        order_ok = expected_order_match(ranked_keys, expected_keys)
        p5_vals.append(p5)
        r10_vals.append(r10)
        mrr_vals.append(mrr)
        order_vals.append(order_ok)
        top_ok = (
            bool(ranked_keys)
            and mem_by_key[ranked_keys[0]]["category"] == expected_top
        )
        if top_ok:
            top_cat_hits += 1
        per_query.append(
            {
                "query_id": query_id,
                "precision_at_5": p5,
                "recall_at_10": r10,
                "mrr": mrr,
                "expected_order_match": order_ok,
                "top_category_ok": top_ok,
                "ranked_content_keys": ranked_keys,
            }
        )

    aggregate = {
        "precision_at_5": macro_mean(p5_vals),
        "recall_at_10": macro_mean(r10_vals),
        "mrr": macro_mean(mrr_vals),
        "expected_order_match": macro_mean(order_vals),
        "top_category_accuracy": top_cat_hits / len(queries) if queries else 0.0,
    }
    failed_queries = [
        q["query_id"]
        for q in per_query
        if (
            q["precision_at_5"] < 1.0
            or q["recall_at_10"] < 1.0
            or q["mrr"] < 1.0
            or q["expected_order_match"] < 1.0
        )
    ]
    if failed_queries:
        sample = ", ".join(failed_queries[:5])
        raise RuntimeError(
            f"ranking bench: {len(failed_queries)} queries below perfect metrics: {sample}"
        )
    result = {
        "benchmark": "ranking_quality",
        "schema_version": 1,
        "gold_set": "v1",
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "org_id": str(seed.org_id),
        "agent_id": str(seed.agent_id),
        "query_count": len(queries),
        "memory_count": len(seed.content_key_to_memory_id),
        "metrics": aggregate,
        "queries": per_query,
    }
    await engine.dispose()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gold", type=Path, default=GOLD_SET_PATH)
    args = parser.parse_args(argv)
    gold_path = resolve_bench_input_path(args.gold, bench_dir=_RANK_DIR)
    result = asyncio.run(run_bench(gold_path=gold_path))
    write_bench_output_json(args.output, bench_dir=_RANK_DIR, payload=result)
    metrics = result["metrics"]
    print(
        f"ranking_quality: precision@5={metrics['precision_at_5']:.4f} "
        f"recall@10={metrics['recall_at_10']:.4f} mrr={metrics['mrr']:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
