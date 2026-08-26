"""Production HNSW cell filter + SLA gate helpers for published history."""

from __future__ import annotations

from typing import Any

_PUBLISH_EF_SEARCH = 40
_PUBLISH_MIN_SIMILARITY = 0.70
_PUBLISH_MIN_SIM_TOLERANCE = 0.001
_PUBLISH_ITERATIVE_SCAN = "off"
_PUBLISH_INDEX_BUILD_MODE = "bulk"
_RECALL_SLA = 0.98
_P95_SLA_MS_1M = 30.0
_P99_SLA_MS_1M = 100.0


def _min_sim_matches(min_sim: object) -> bool:
    if min_sim is None:
        return False
    try:
        return abs(float(min_sim) - _PUBLISH_MIN_SIMILARITY) <= _PUBLISH_MIN_SIM_TOLERANCE
    except (TypeError, ValueError):
        return False


def _is_production_cell(result: dict[str, Any]) -> bool:
    if result.get("ef_search") != _PUBLISH_EF_SEARCH:
        return False
    if not _min_sim_matches(result.get("min_similarity")):
        return False
    if result.get("iterative_scan", _PUBLISH_ITERATIVE_SCAN) != _PUBLISH_ITERATIVE_SCAN:
        return False
    if result.get("index_build_mode", _PUBLISH_INDEX_BUILD_MODE) != _PUBLISH_INDEX_BUILD_MODE:
        return False
    return True


def filter_published_results(results: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict) and _is_production_cell(item):
            out.append(item)
    return out


def _empty_gate_summary() -> dict[str, Any]:
    return {
        "recall_ok": False,
        "recall_floor": _RECALL_SLA,
        "worst_recall_at_10": 0.0,
        "has_1m": False,
        "note": "no production cells after filter",
    }


def _attach_1m_latency(summary: dict[str, Any], at_1m: dict[str, Any]) -> None:
    p95 = float(at_1m["latency_ms_p95"])
    p99 = float(at_1m["latency_ms_p99"])
    summary["p95_ms_1m"] = p95
    summary["p99_ms_1m"] = p99
    summary["p95_1m_ok"] = p95 < _P95_SLA_MS_1M
    summary["p99_1m_ok"] = p99 < _P99_SLA_MS_1M


def compute_gate_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return _empty_gate_summary()
    recalls = [float(r["recall_at_10"]) for r in results]
    worst = min(recalls)
    at_1m = next((r for r in results if int(r["corpus_size"]) >= 1_000_000), None)
    summary: dict[str, Any] = {
        "recall_ok": worst >= _RECALL_SLA,
        "recall_floor": _RECALL_SLA,
        "worst_recall_at_10": worst,
        "has_1m": at_1m is not None,
    }
    if at_1m is not None:
        _attach_1m_latency(summary, at_1m)
    else:
        summary["note"] = "1M cell absent (expected on smoke/fast profiles)"
    return summary


def _1m_latency_failed(gate: dict[str, Any]) -> bool:
    if not gate.get("has_1m"):
        return False
    return not gate.get("p95_1m_ok", True) or not gate.get("p99_1m_ok", True)


def compute_status(gate: dict[str, Any]) -> str:
    """Gate status for published runs.

    Missing 1M on smoke/fast is expected coverage deferral, not a soft failure.
    PR comments show an informational "1M deferred" badge instead of WARN.
    """
    if not gate.get("recall_ok", False):
        return "fail"
    if _1m_latency_failed(gate):
        return "fail"
    return "pass"


# Re-exported constants used by build_published_data merge messaging.
PUBLISH_EF_SEARCH = _PUBLISH_EF_SEARCH
PUBLISH_MIN_SIMILARITY = _PUBLISH_MIN_SIMILARITY
PUBLISH_ITERATIVE_SCAN = _PUBLISH_ITERATIVE_SCAN
PUBLISH_INDEX_BUILD_MODE = _PUBLISH_INDEX_BUILD_MODE
