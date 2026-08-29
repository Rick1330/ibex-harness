"""Re-export plan assertion helpers for integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BENCH_MEMORY = _REPO_ROOT / "benchmarks" / "memory"
for path in (_REPO_ROOT, _BENCH_MEMORY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from benchmarks.memory.corpus import gin_idx_scan_count, idx_scan_count
from benchmarks.memory.plan_assert import (
    assert_gin_index_scanned,
    assert_gin_index_used,
    assert_hnsw_index_scanned,
    assert_hnsw_index_used,
)
from benchmarks.memory.plan_explain import (
    GinExplainParams,
    HnswExplainParams,
    explain_gin_probe_plan,
    explain_hnsw_search_plan,
    run_gin_probe,
)

hnsw_idx_scan_count = idx_scan_count

__all__ = [
    "GinExplainParams",
    "HnswExplainParams",
    "assert_gin_index_scanned",
    "assert_gin_index_used",
    "assert_hnsw_index_scanned",
    "assert_hnsw_index_used",
    "explain_gin_probe_plan",
    "explain_hnsw_search_plan",
    "gin_idx_scan_count",
    "hnsw_idx_scan_count",
    "run_gin_probe",
]
