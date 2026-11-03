"""Retrieval-quality and labelling metrics shared by the benchmark and the read path.

The multi-mode benchmark (5.C.2) and the shadow comparison (5.C.3) must report the same
numbers, so those numbers live here rather than in `benchmarks/`. The benchmark puts
`services/memory` on `PYTHONPATH`; the shadow emitter is production code and must not
import from `benchmarks/`.

Definitions and the reasoning behind them are recorded in ADR-0095.
"""

from __future__ import annotations

from app.eval.agreement import KappaResult, cohen_kappa
from app.eval.ranking import ndcg_at_k, rbo, top1_agreement

__all__ = [
    "KappaResult",
    "cohen_kappa",
    "ndcg_at_k",
    "rbo",
    "top1_agreement",
]
