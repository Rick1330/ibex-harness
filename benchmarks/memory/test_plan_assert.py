"""Unit tests for EXPLAIN plan assertion helpers."""

from __future__ import annotations

import pytest

from plan_assert import (
    PlanAssertionError,
    assert_gin_index_used,
    walk_plan_nodes,
)

_GIN_PLAN = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Plans": [
                {
                    "Node Type": "Bitmap Index Scan",
                    "Index Name": "idx_memories_search_vector",
                    "Relation Name": "memories",
                    "Actual Rows": 1,
                }
            ],
        },
        "Planning Time": 0.1,
        "Execution Time": 0.2,
    }
]

_BTREE_PLAN = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Plans": [
                {
                    "Node Type": "Index Scan",
                    "Index Name": "idx_memories_agent_active",
                    "Relation Name": "memories",
                    "Actual Rows": 1,
                }
            ],
        }
    }
]

_NESTED_PLAN = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Plans": [
                {
                    "Node Type": "Bitmap Heap Scan",
                    "Relation Name": "memories",
                    "Plans": [
                        {
                            "Node Type": "Bitmap Index Scan",
                            "Index Name": "idx_memories_search_vector",
                            "Actual Rows": 5,
                        }
                    ],
                }
            ],
        },
        "Execution Time": 1.5,
    }
]


def test_walk_plan_nodes_flattens_nested_plans() -> None:
    nodes = walk_plan_nodes(_NESTED_PLAN[0]["Plan"])
    index_names = [node.get("Index Name") for node in nodes]
    assert "idx_memories_search_vector" in index_names


def test_assert_gin_index_used_accepts_bitmap_index_scan() -> None:
    summary = assert_gin_index_used(_GIN_PLAN)
    assert summary["index_name"] == "idx_memories_search_vector"
    assert summary["node_type"] == "Bitmap Index Scan"
    assert summary["actual_rows"] == 1


def test_assert_gin_index_used_accepts_nested_bitmap_tree() -> None:
    summary = assert_gin_index_used(_NESTED_PLAN)
    assert summary["index_name"] == "idx_memories_search_vector"


def test_assert_gin_index_used_rejects_btree_plan() -> None:
    with pytest.raises(PlanAssertionError, match="idx_memories_search_vector"):
        assert_gin_index_used(_BTREE_PLAN)

    with pytest.raises(PlanAssertionError, match="idx_memories_agent_active"):
        assert_gin_index_used(_BTREE_PLAN)
