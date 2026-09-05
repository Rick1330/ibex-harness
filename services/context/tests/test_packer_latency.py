"""Latency smoke for ContextPacker DP path (milestone 3.5.C.4 / ADR-0069).

Asserts packing-only p99 < 5ms at n=70 (ARCHITECTURE.md / milestone success
signal). PERFORMANCE.md's ≤15ms ranking+packing @100 remains a separate
combined envelope — documented reconciliation follow-up in ADR-0069.
"""

from __future__ import annotations

import time
from uuid import uuid4

from app.capability_catalog import TokenizerFamilyPolicy
from app.estimate import ESTIMATE_CHARS_DIV_4
from app.packer import ContextPacker, ScoredMemory
from app.retrieval import MemoryHit

_WARMUP = 20
_ITERS = 200
_N = 70
_P99_BUDGET_MS = 5.0
_TOKEN_BUDGET = 8000
_POLICY = TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02)


def _percentile_ms(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, int(len(ordered) * percentile) - 1)
    return ordered[index]


def _fixture(n: int) -> tuple[list[ScoredMemory], ContextPacker]:
    org = str(uuid4())
    agent = str(uuid4())
    scored: list[ScoredMemory] = []
    for i in range(n):
        # Vary content length (~4–200 tokens under chars_div_4).
        tokens = 4 + (i * 3) % 50
        content = "m" * (4 * tokens)
        hit = MemoryHit(
            memory_id=str(uuid4()),
            org_id=org,
            agent_id=agent,
            content=content,
            category="factual" if i % 2 == 0 else "episodic",
            confidence=0.5 + (i % 5) * 0.1,
            similarity=0.4 + (i % 6) * 0.1,
            rank=i + 1,
            source="vector",
        )
        scored.append(ScoredMemory(hit=hit, composite_score=0.3 + (i % 10) * 0.07))
    return scored, ContextPacker(_POLICY)


def test_packer_dp_latency_p99_under_5ms_at_n70() -> None:
    scored, packer = _fixture(_N)
    for _ in range(_WARMUP):
        packer.pack(scored, _TOKEN_BUDGET)

    samples_ms: list[float] = []
    for _ in range(_ITERS):
        start = time.perf_counter()
        packed = packer.pack(scored, _TOKEN_BUDGET)
        samples_ms.append((time.perf_counter() - start) * 1000.0)
        assert packed.path == "dp"
        assert packed.total_tokens <= _TOKEN_BUDGET

    p50 = _percentile_ms(samples_ms, 0.50)
    p99 = _percentile_ms(samples_ms, 0.99)
    print(
        f"context_packer_latency n={_N} budget={_TOKEN_BUDGET} "
        f"p50_ms={p50:.3f} p99_ms={p99:.3f} iterations={_ITERS}"
    )
    assert p99 < _P99_BUDGET_MS, (
        f"packer p99 {p99:.3f}ms exceeds {_P99_BUDGET_MS}ms packing budget at n={_N}"
    )
