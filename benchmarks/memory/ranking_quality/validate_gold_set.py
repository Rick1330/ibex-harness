#!/usr/bin/env python3
"""Validate gold_set_v1.json structure and composite-ranking consistency."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MEMORY_DIR = Path(__file__).resolve().parents[3] / "services" / "memory"
_BENCH_MEMORY = Path(__file__).resolve().parents[1]
_RANK_DIR = Path(__file__).resolve().parent
for path in (_MEMORY_DIR, _BENCH_MEMORY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.scoring.composite import CompositeInputs, composite_score  # noqa: E402
from path_guard import resolve_bench_input_path  # noqa: E402

CATEGORIES = frozenset({"factual", "procedural", "preference", "behavioral", "episodic"})
DECAY_QUERY_IDS = frozenset(
    {
        "q_pref_theme_decay",
        "q_workflow_deploy_decay",
        "q_confidence_tie_break",
    }
)
MIN_MEMORIES = 30
MAX_MEMORIES = 55
MIN_QUERIES = 15
MAX_QUERIES = 25
MIN_AGE_DAYS = 7
MAX_AGE_DAYS = 180
EMBEDDING_DIM = 1024
REQUIRED_MEMORY_FIELDS = (
    "content_key",
    "content",
    "category",
    "valid_from_days_ago",
    "embedding_hotspot",
    "confidence",
    "usefulness_score",
)


@dataclass
class QueryValidationState:
    mem_by_key: dict[str, dict[str, Any]]
    query_ids: set[str]
    decay_found: set[str]


@dataclass(frozen=True)
class CompositeOrderCheck:
    prefix: str
    qid: str
    hotspot: int
    expected: list[object]
    mem_by_key: dict[str, dict[str, Any]]


def _unit_interval(value: object, field: str, prefix: str) -> list[str]:
    errors: list[str] = []
    if value is None:
        errors.append(f"{prefix} missing {field}")
        return errors
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        errors.append(f"{prefix} {field} must be numeric")
        return errors
    if parsed < 0.0 or parsed > 1.0:
        errors.append(f"{prefix} {field} must be in [0, 1], got {parsed!r}")
    return errors


def _is_unit_interval(value: object) -> bool:
    if value is None:
        return False
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return 0.0 <= parsed <= 1.0


def _composite(mem: dict[str, Any]) -> float:
    return composite_score(
        CompositeInputs(
            relevance=1.0,
            age_days=float(mem["valid_from_days_ago"]),
            categories=(mem["category"],),
            usefulness=float(mem["usefulness_score"]),
            confidence=float(mem["confidence"]),
            access_frequency=0.0,
        )
    )


def _composite_safe(mem: dict[str, Any]) -> float | None:
    """Return composite score when required fields are present and valid."""
    if not _is_unit_interval(mem.get("confidence")):
        return None
    if not _is_unit_interval(mem.get("usefulness_score")):
        return None
    try:
        return _composite(mem)
    except (KeyError, TypeError, ValueError):
        return None


def _parse_int(value: object, field: str, prefix: str) -> tuple[int | None, list[str]]:
    if value is None:
        return None, [f"{prefix} missing {field}"]
    if isinstance(value, bool):
        return None, [f"{prefix} {field} must be an integer"]
    if isinstance(value, float) and not value.is_integer():
        return None, [f"{prefix} {field} must be an integer"]
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, [f"{prefix} {field} must be an integer"]
    return parsed, []


def _require_non_empty_str(value: object, field: str, prefix: str) -> tuple[str | None, list[str]]:
    if not isinstance(value, str):
        return None, [f"{prefix} {field} must be a string"]
    if not value.strip():
        return None, [f"{prefix} {field} must be non-empty"]
    return value, []


def _validate_memory_required_keys(row: dict[str, Any], prefix: str) -> list[str]:
    return [
        f"{prefix} missing {field}"
        for field in REQUIRED_MEMORY_FIELDS
        if field not in row
    ]


def _validate_memory_scalar_fields(row: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    errors.extend(_unit_interval(row.get("confidence"), "confidence", prefix))
    errors.extend(
        _unit_interval(row.get("usefulness_score"), "usefulness_score", prefix)
    )
    key = str(row.get("content_key", ""))
    if not key:
        errors.append(f"{prefix} content_key must be non-empty")
    category = row.get("category")
    if not isinstance(category, str):
        errors.append(f"{prefix} category must be a string")
    elif category not in CATEGORIES:
        errors.append(f"{prefix} invalid category {category!r}")
    age, age_errors = _parse_int(row.get("valid_from_days_ago"), "valid_from_days_ago", prefix)
    errors.extend(age_errors)
    if age is not None and not (MIN_AGE_DAYS <= age <= MAX_AGE_DAYS):
        errors.append(f"{prefix} age {age} outside [{MIN_AGE_DAYS}, {MAX_AGE_DAYS}]")
    hotspot, hotspot_errors = _parse_int(
        row.get("embedding_hotspot"), "embedding_hotspot", prefix
    )
    errors.extend(hotspot_errors)
    if hotspot is not None and not (0 <= hotspot < EMBEDDING_DIM):
        errors.append(f"{prefix} hotspot {hotspot} out of range")
    return errors


def _validate_memory_content(row: dict[str, Any], prefix: str) -> list[str]:
    content = row.get("content")
    if not isinstance(content, str):
        return [f"{prefix} content must be a string"]
    if not content.strip():
        return [f"{prefix} content must be non-empty"]
    errors: list[str] = []
    if len(content) < 20:
        errors.append(f"{prefix} content too short")
    if content.startswith(("gold ranking", "gold distractor")):
        errors.append(f"{prefix} content looks like placeholder text")
    return errors


def _validate_memory_row(row: dict[str, Any], prefix: str) -> list[str]:
    errors = _validate_memory_required_keys(row, prefix)
    errors.extend(_validate_memory_scalar_fields(row, prefix))
    errors.extend(_validate_memory_content(row, prefix))
    return errors


def _validate_expected_content_keys(
    expected: list[object],
    *,
    prefix: str,
    mem_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for key in expected:
        if not isinstance(key, str):
            errors.append(f"{prefix} expected_content_keys items must be strings")
            continue
        if key not in mem_by_key:
            errors.append(f"{prefix} references unknown content_key {key!r}")
    return errors


def _validate_query_composite_order(check: CompositeOrderCheck) -> list[str]:
    cluster = [
        m
        for m in check.mem_by_key.values()
        if int(m["embedding_hotspot"]) == check.hotspot
    ]
    if any(_composite_safe(m) is None for m in cluster):
        return []
    ranked = sorted(cluster, key=lambda m: (-_composite(m), m["content_key"]))
    actual_order = [m["content_key"] for m in ranked]
    if actual_order == check.expected:
        return []
    return [
        f"{check.prefix} ({check.qid}) expected order does not match composite simulation\n"
        f"  expected: {check.expected}\n"
        f"  composite: {actual_order}"
    ]


def _validate_top_category(
    expected: list[object],
    row: dict[str, Any],
    *,
    prefix: str,
    mem_by_key: dict[str, dict[str, Any]],
) -> list[str]:
    top_key = expected[0]
    if not isinstance(top_key, str):
        return [f"{prefix} first expected_content_key must be a string"]
    top_cat = row.get("expected_top_category")
    if top_key not in mem_by_key:
        return [f"{prefix} references unknown first expected content_key {top_key!r}"]
    if mem_by_key[top_key]["category"] == top_cat:
        return []
    return [
        f"{prefix} expected_top_category {top_cat!r} != "
        f"first key category {mem_by_key[top_key]['category']!r}"
    ]


def _validate_query_identity(
    row: dict[str, Any],
    *,
    prefix: str,
    query_ids: set[str],
    decay_found: set[str],
) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    qid, qid_errors = _require_non_empty_str(row.get("query_id"), "query_id", prefix)
    errors.extend(qid_errors)
    if qid is None:
        return None, errors
    if qid in query_ids:
        errors.append(f"duplicate query_id: {qid}")
    query_ids.add(qid)
    if qid in DECAY_QUERY_IDS:
        decay_found.add(qid)
    _, query_text_errors = _require_non_empty_str(
        row.get("query_text"), "query_text", prefix
    )
    errors.extend(query_text_errors)
    return qid, errors


def _validate_query_expectations(
    row: dict[str, Any],
    *,
    prefix: str,
    qid: str,
    state: QueryValidationState,
) -> list[str]:
    errors: list[str] = []
    hotspot, hotspot_errors = _parse_int(row.get("query_hotspot"), "query_hotspot", prefix)
    errors.extend(hotspot_errors)
    if hotspot is not None and not (0 <= hotspot < EMBEDDING_DIM):
        errors.append(f"{prefix} query_hotspot {hotspot} out of range")
    expected = row.get("expected_content_keys")
    if not isinstance(expected, list) or not expected:
        errors.append(f"{prefix} expected_content_keys must be non-empty array")
        return errors
    errors.extend(
        _validate_expected_content_keys(
            expected, prefix=prefix, mem_by_key=state.mem_by_key
        )
    )
    if hotspot is None:
        return errors
    errors.extend(
        _validate_query_composite_order(
            CompositeOrderCheck(
                prefix=prefix,
                qid=qid,
                hotspot=hotspot,
                expected=expected,
                mem_by_key=state.mem_by_key,
            )
        )
    )
    errors.extend(
        _validate_top_category(
            expected, row, prefix=prefix, mem_by_key=state.mem_by_key
        )
    )
    return errors


def _validate_query_row(
    row: dict[str, Any],
    *,
    index: int,
    state: QueryValidationState,
) -> list[str]:
    prefix = f"queries[{index}]"
    qid, errors = _validate_query_identity(
        row,
        prefix=prefix,
        query_ids=state.query_ids,
        decay_found=state.decay_found,
    )
    if qid is None:
        return errors
    errors.extend(
        _validate_query_expectations(
            row,
            prefix=prefix,
            qid=qid,
            state=state,
        )
    )
    return errors


def _index_memories(memories: list[object]) -> tuple[dict[str, dict[str, Any]], Counter[str], list[str]]:
    mem_by_key: dict[str, dict[str, Any]] = {}
    cat_counts: Counter[str] = Counter()
    errors: list[str] = []

    for index, row in enumerate(memories):
        prefix = f"memories[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        row_errors = _validate_memory_row(row, prefix)
        key = str(row.get("content_key", ""))
        if key and key in mem_by_key:
            row_errors.append(f"duplicate content_key: {key}")
        if row_errors:
            errors.extend(row_errors)
            continue
        mem_by_key[key] = row
        cat_counts[str(row["category"])] += 1

    return mem_by_key, cat_counts, errors


def _validate_collection_sizes(memories: list[object], queries: list[object]) -> list[str]:
    errors: list[str] = []
    if not (MIN_MEMORIES <= len(memories) <= MAX_MEMORIES):
        errors.append(f"memory count {len(memories)} outside [{MIN_MEMORIES}, {MAX_MEMORIES}]")
    if not (MIN_QUERIES <= len(queries) <= MAX_QUERIES):
        errors.append(f"query count {len(queries)} outside [{MIN_QUERIES}, {MAX_QUERIES}]")
    return errors


def _validate_category_coverage(cat_counts: Counter[str]) -> list[str]:
    return [
        f"category {cat!r} has only {cat_counts[cat]} memories (need >= 3)"
        for cat in CATEGORIES
        if cat_counts[cat] < 3
    ]


def _validate_queries(
    queries: list[object],
    mem_by_key: dict[str, dict[str, Any]],
) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    state = QueryValidationState(
        mem_by_key=mem_by_key,
        query_ids=set(),
        decay_found=set(),
    )
    for index, row in enumerate(queries):
        if not isinstance(row, dict):
            errors.append(f"queries[{index}] must be an object")
            continue
        errors.extend(_validate_query_row(row, index=index, state=state))
    return errors, state.decay_found


def validate_gold_set(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["gold set must be an object"]
    memories = payload.get("memories")
    queries = payload.get("queries")
    if not isinstance(memories, list):
        return ["memories must be an array"]
    if not isinstance(queries, list):
        return ["queries must be an array"]

    errors = _validate_collection_sizes(memories, queries)
    mem_by_key, cat_counts, memory_errors = _index_memories(memories)
    errors.extend(memory_errors)
    errors.extend(_validate_category_coverage(cat_counts))

    query_errors, decay_found = _validate_queries(queries, mem_by_key)
    errors.extend(query_errors)

    missing_decay = DECAY_QUERY_IDS - decay_found
    if missing_decay:
        errors.append(f"missing decay queries: {sorted(missing_decay)}")

    return errors


def main(argv: list[str] | None = None) -> int:
    path = _RANK_DIR / "gold_set_v1.json"
    if argv and len(argv) > 1:
        path = resolve_bench_input_path(Path(argv[1]), bench_dir=_RANK_DIR)
    payload = json.loads(path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083
    errors = validate_gold_set(payload)
    if errors:
        print(f"gold set validation failed ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"ok: {len(payload['memories'])} memories, "
        f"{len(payload['queries'])} queries, "
        f"{len(DECAY_QUERY_IDS)} decay cases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
