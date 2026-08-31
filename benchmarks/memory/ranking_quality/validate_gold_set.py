#!/usr/bin/env python3
"""Validate gold_set_v1.json structure and composite-ranking consistency."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_MEMORY_DIR = Path(__file__).resolve().parents[3] / "services" / "memory"
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from app.scoring.composite import CompositeInputs, composite_score  # noqa: E402

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


def validate_gold_set(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    memories = payload.get("memories")
    queries = payload.get("queries")
    if not isinstance(memories, list):
        return ["memories must be an array"]
    if not isinstance(queries, list):
        return ["queries must be an array"]
    if not (MIN_MEMORIES <= len(memories) <= MAX_MEMORIES):
        errors.append(f"memory count {len(memories)} outside [{MIN_MEMORIES}, {MAX_MEMORIES}]")
    if not (MIN_QUERIES <= len(queries) <= MAX_QUERIES):
        errors.append(f"query count {len(queries)} outside [{MIN_QUERIES}, {MAX_QUERIES}]")

    mem_by_key: dict[str, dict[str, Any]] = {}
    cat_counts: Counter[str] = Counter()
    hotspots: set[int] = set()

    for index, row in enumerate(memories):
        prefix = f"memories[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in (
            "content_key",
            "content",
            "category",
            "valid_from_days_ago",
            "embedding_hotspot",
            "confidence",
            "usefulness_score",
        ):
            if field not in row:
                errors.append(f"{prefix} missing {field}")
        errors.extend(_unit_interval(row.get("confidence"), "confidence", prefix))
        errors.extend(
            _unit_interval(row.get("usefulness_score"), "usefulness_score", prefix)
        )
        key = str(row.get("content_key", ""))
        if key in mem_by_key:
            errors.append(f"duplicate content_key: {key}")
        if row.get("category") not in CATEGORIES:
            errors.append(f"{prefix} invalid category {row.get('category')!r}")
        age = int(row.get("valid_from_days_ago", -1))
        if not (MIN_AGE_DAYS <= age <= MAX_AGE_DAYS):
            errors.append(f"{prefix} age {age} outside [{MIN_AGE_DAYS}, {MAX_AGE_DAYS}]")
        hotspot = int(row.get("embedding_hotspot", -1))
        if not (0 <= hotspot < EMBEDDING_DIM):
            errors.append(f"{prefix} hotspot {hotspot} out of range")
        content = str(row.get("content", ""))
        if len(content) < 20:
            errors.append(f"{prefix} content too short")
        if content.startswith("gold ranking") or content.startswith("gold distractor"):
            errors.append(f"{prefix} content looks like placeholder text")
        mem_by_key[key] = row
        cat_counts[str(row["category"])] += 1
        hotspots.add(hotspot)

    for cat in CATEGORIES:
        if cat_counts[cat] < 3:
            errors.append(f"category {cat!r} has only {cat_counts[cat]} memories (need >= 3)")

    query_ids: set[str] = set()
    decay_found: set[str] = set()

    for index, row in enumerate(queries):
        prefix = f"queries[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        qid = str(row.get("query_id", ""))
        if qid in query_ids:
            errors.append(f"duplicate query_id: {qid}")
        query_ids.add(qid)
        if qid in DECAY_QUERY_IDS:
            decay_found.add(qid)

        hotspot = int(row.get("query_hotspot", -1))
        expected = row.get("expected_content_keys")
        if not isinstance(expected, list) or not expected:
            errors.append(f"{prefix} expected_content_keys must be non-empty array")
            continue
        for key in expected:
            if key not in mem_by_key:
                errors.append(f"{prefix} references unknown content_key {key!r}")

        cluster = [m for m in memories if int(m["embedding_hotspot"]) == hotspot]
        if any(_composite_safe(m) is None for m in cluster):
            continue
        ranked = sorted(cluster, key=lambda m: (-_composite(m), m["content_key"]))
        actual_order = [m["content_key"] for m in ranked]
        if actual_order != expected:
            errors.append(
                f"{prefix} ({qid}) expected order does not match composite simulation\n"
                f"  expected: {expected}\n"
                f"  composite: {actual_order}"
            )
        top_key = expected[0]
        top_cat = row.get("expected_top_category")
        if mem_by_key[top_key]["category"] != top_cat:
            errors.append(
                f"{prefix} expected_top_category {top_cat!r} != "
                f"first key category {mem_by_key[top_key]['category']!r}"
            )

    missing_decay = DECAY_QUERY_IDS - decay_found
    if missing_decay:
        errors.append(f"missing decay queries: {sorted(missing_decay)}")

    return errors


def main(argv: list[str] | None = None) -> int:
    path = Path(__file__).resolve().parent / "gold_set_v1.json"
    if argv and len(argv) > 1:
        path = Path(argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
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
