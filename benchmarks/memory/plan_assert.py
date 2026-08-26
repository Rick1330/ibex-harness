"""Assert pgvector HNSW plans from EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)."""

from __future__ import annotations

from typing import Any

_HNSW_INDEX = "idx_memories_embedding_hnsw"


class PlanAssertionError(RuntimeError):
    """Raised when the planner does not use idx_memories_embedding_hnsw."""


def walk_plan_nodes(node: Any) -> list[dict[str, Any]]:
    """Flatten nested EXPLAIN JSON Plan trees into a list of node dicts."""
    if not isinstance(node, dict):
        return []
    out = [node]
    for key in ("Plans", "Plan"):
        child = node.get(key)
        if isinstance(child, list):
            for item in child:
                out.extend(walk_plan_nodes(item))
        elif isinstance(child, dict):
            out.extend(walk_plan_nodes(child))
    return out


def collect_buffer_stats(nodes: list[dict[str, Any]]) -> dict[str, int]:
    hits = 0
    reads = 0
    for node in nodes:
        hits += int(node.get("Shared Hit Blocks") or 0)
        reads += int(node.get("Shared Read Blocks") or 0)
    return {"shared_hit_blocks": hits, "shared_read_blocks": reads}


def _is_hnsw_access(node: dict[str, Any]) -> bool:
    ntype = str(node.get("Node Type") or "")
    index_name = str(node.get("Index Name") or "")
    return _HNSW_INDEX in index_name and ("Index" in ntype or "Bitmap" in ntype)


def _is_seq_on_memories(node: dict[str, Any]) -> bool:
    ntype = str(node.get("Node Type") or "")
    relation = str(node.get("Relation Name") or "")
    return ntype == "Seq Scan" and relation in {"memories", "ibex_core.memories"}


def _summarize_nodes(nodes: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{n.get('Node Type')}@{n.get('Relation Name') or n.get('Index Name')}"
        for n in nodes[:12]
    )


def _root_plan(explain_json: list[Any] | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    root = explain_json[0] if isinstance(explain_json, list) else explain_json
    if not isinstance(root, dict):
        raise PlanAssertionError(f"unexpected EXPLAIN root type: {type(root)!r}")
    plan = root.get("Plan")
    if not isinstance(plan, dict):
        raise PlanAssertionError("EXPLAIN JSON missing Plan")
    return root, plan


def _require_hnsw_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hnsw_nodes = [n for n in nodes if _is_hnsw_access(n)]
    if hnsw_nodes:
        return hnsw_nodes
    seq_on_memories = any(_is_seq_on_memories(n) for n in nodes)
    seq_note = "; Seq Scan on memories also present" if seq_on_memories else ""
    raise PlanAssertionError(
        "expected Index Scan / Bitmap Index Scan on idx_memories_embedding_hnsw; "
        f"saw: {_summarize_nodes(nodes)}{seq_note}"
    )


def _plan_summary(
    root: dict[str, Any], primary: dict[str, Any], buffers: dict[str, int]
) -> dict[str, Any]:
    return {
        "node_type": primary.get("Node Type"),
        "index_name": primary.get("Index Name"),
        "relation": primary.get("Relation Name"),
        "actual_rows": primary.get("Actual Rows"),
        "planning_time_ms": root.get("Planning Time"),
        "execution_time_ms": root.get("Execution Time"),
        **buffers,
    }


def assert_hnsw_index_used(explain_json: list[Any] | dict[str, Any]) -> dict[str, Any]:
    """Require an Index/Bitmap Index Scan on idx_memories_embedding_hnsw."""
    root, plan = _root_plan(explain_json)
    nodes = walk_plan_nodes(plan)
    hnsw_nodes = _require_hnsw_nodes(nodes)
    return _plan_summary(root, hnsw_nodes[0], collect_buffer_stats(nodes))
