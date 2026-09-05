#!/usr/bin/env python3
"""Ranking-quality benchmark — gold set via MemoryReadRepository.find_similar."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
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
from seed import GOLD_SET_PATH, GoldSeedResult, load_gold_set, seed_gold_set  # noqa: E402
from validate_gold_set import validate_gold_set  # noqa: E402

DEFAULT_OUTPUT = _RANK_DIR / "output" / "latest.json"


@dataclass(frozen=True, slots=True)
class QueryEvalContext:
    seed: GoldSeedResult
    id_to_key: dict[str, str]
    mem_by_key: dict[str, dict]


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


async def _evaluate_relevance_gate_probe(
    repo: MemoryReadRepository,
    ctx: QueryEvalContext,
) -> dict:
    """Open retrieval (min_similarity=0.0) so orthogonal bait can reach scoring.

    Gold-set queries use min_similarity=0.5, so floors ≤0.30 never filter them.
    This probe intentionally opens ANN so the scoring-time floor must exclude
    ``gold.noise.relevance_gate_bait`` (sim≈0, high confidence/usefulness/frequency).
    """
    bait_key = "gold.noise.relevance_gate_bait"
    relevant_key = "gold.factual.notification_channel"
    if bait_key not in ctx.mem_by_key:
        msg = f"gold set missing gate bait memory {bait_key!r}"
        raise RuntimeError(msg)
    if relevant_key not in ctx.mem_by_key:
        msg = f"gold set missing gate probe relevant memory {relevant_key!r}"
        raise RuntimeError(msg)

    # Hotspot 1 cluster (sim=1.0) + opened retrieval pulls orthogonal bait (sim=0.0).
    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=ctx.seed.org_id,
            agent_id=ctx.seed.agent_id,
            query_embedding=zero_embedding(hotspot=1),
            query_text="notification preferences relevance gate probe",
            limit=50,
            min_similarity=0.0,
        )
    )
    ranked_keys = [
        ctx.id_to_key[str(hit.id)] for hit in results if str(hit.id) in ctx.id_to_key
    ]
    bait_excluded = bait_key not in ranked_keys
    relevant_present = relevant_key in ranked_keys
    if not bait_excluded:
        msg = (
            "relevance gate probe failed: bait "
            f"{bait_key!r} appeared in ranked results under min_similarity=0.0"
        )
        raise RuntimeError(msg)
    if not relevant_present:
        msg = (
            "relevance gate probe failed: expected relevant "
            f"{relevant_key!r} missing from ranked results"
        )
        raise RuntimeError(msg)
    return {
        "bait_content_key": bait_key,
        "relevant_content_key": relevant_key,
        "min_similarity": 0.0,
        "limit": 50,
        "bait_excluded": bait_excluded,
        "relevant_present": relevant_present,
        "ranked_count": len(ranked_keys),
    }


async def _evaluate_query(
    repo: MemoryReadRepository,
    row: dict,
    ctx: QueryEvalContext,
) -> tuple[dict, bool]:
    query_id = str(row["query_id"])
    hotspot = int(row["query_hotspot"])
    expected_keys = list(row["expected_content_keys"])
    expected_top = str(row.get("expected_top_category", ""))
    query_vec = zero_embedding(hotspot=hotspot)

    results = await repo.find_similar(
        FindSimilarQuery(
            org_id=ctx.seed.org_id,
            agent_id=ctx.seed.agent_id,
            query_embedding=query_vec,
            query_text=str(row["query_text"]),
            limit=10,
            min_similarity=0.5,
        )
    )
    ranked_keys = [
        ctx.id_to_key[str(hit.id)] for hit in results if str(hit.id) in ctx.id_to_key
    ]
    p5 = precision_at_k(ranked_keys, expected_keys, 5)
    r10 = recall_at_k(ranked_keys, expected_keys, 10)
    mrr = mean_reciprocal_rank(ranked_keys, expected_keys)
    order_ok = expected_order_match(ranked_keys, expected_keys)
    top_ok = (
        bool(ranked_keys) and ctx.mem_by_key[ranked_keys[0]]["category"] == expected_top
    )
    return (
        {
            "query_id": query_id,
            "precision_at_5": p5,
            "recall_at_10": r10,
            "mrr": mrr,
            "expected_order_match": order_ok,
            "top_category_ok": top_ok,
            "ranked_content_keys": ranked_keys,
        },
        top_ok,
    )


def _aggregate_metrics(per_query: list[dict], *, top_cat_hits: int) -> dict:
    p5_vals = [float(q["precision_at_5"]) for q in per_query]
    r10_vals = [float(q["recall_at_10"]) for q in per_query]
    mrr_vals = [float(q["mrr"]) for q in per_query]
    order_vals = [float(q["expected_order_match"]) for q in per_query]
    return {
        "precision_at_5": macro_mean(p5_vals),
        "recall_at_10": macro_mean(r10_vals),
        "mrr": macro_mean(mrr_vals),
        "expected_order_match": macro_mean(order_vals),
        "top_category_accuracy": top_cat_hits / len(per_query) if per_query else 0.0,
    }


def _assert_perfect_metrics(per_query: list[dict]) -> None:
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


async def run_bench(*, gold_path: Path) -> dict:
    settings = Settings(database_url=_async_dsn()).model_copy(
        update={"search_fallback_enabled": False},
    )
    engine = create_engine(settings)
    try:
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
        top_cat_hits = 0
        eval_ctx = QueryEvalContext(
            seed=seed,
            id_to_key=id_to_key,
            mem_by_key=mem_by_key,
        )
        for row in queries:
            query_result, top_ok = await _evaluate_query(repo, row, eval_ctx)
            per_query.append(query_result)
            if top_ok:
                top_cat_hits += 1

        aggregate = _aggregate_metrics(per_query, top_cat_hits=top_cat_hits)
        _assert_perfect_metrics(per_query)
        gate_probe = await _evaluate_relevance_gate_probe(repo, eval_ctx)
        return {
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
            "relevance_gate_probe": gate_probe,
        }
    finally:
        await engine.dispose()


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
