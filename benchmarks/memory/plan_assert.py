"""Assert pgvector HNSW plans from EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)."""

from __future__ import annotations

from typing import Any


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


def assert_hnsw_index_used(explain_json: list[Any] | dict[str, Any]) -> dict[str, Any]:
    """Require an Index/Bitmap Index Scan on idx_memories_embedding_hnsw.

    Fails loudly if a Seq Scan on memories is the ANN access path without HNSW.
    """
    root = explain_json[0] if isinstance(explain_json, list) else explain_json
    if not isinstance(root, dict):
        raise PlanAssertionError(f"unexpected EXPLAIN root type: {type(root)!r}")
    plan = root.get("Plan")
    if not isinstance(plan, dict):
        raise PlanAssertionError("EXPLAIN JSON missing Plan")

    nodes = walk_plan_nodes(plan)
    hnsw_nodes: list[dict[str, Any]] = []
    seq_on_memories = False
    for node in nodes:
        ntype = str(node.get("Node Type") or "")
        relation = str(node.get("Relation Name") or "")
        index_name = str(node.get("Index Name") or "")
        if "idx_memories_embedding_hnsw" in index_name:
            if "Index" in ntype or "Bitmap" in ntype:
                hnsw_nodes.append(node)
        if ntype == "Seq Scan" and relation in {"memories", "ibex_core.memories"}:
            seq_on_memories = True

    if not hnsw_nodes:
        detail = ", ".join(
            f"{n.get('Node Type')}@{n.get('Relation Name') or n.get('Index Name')}"
            for n in nodes[:12]
        )
        raise PlanAssertionError(
            "expected Index Scan / Bitmap Index Scan on idx_memories_embedding_hnsw; "
            f"saw: {detail}"
        )
    if seq_on_memories and not hnsw_nodes:
        raise PlanAssertionError("Seq Scan on memories without HNSW index use")

    buffers = collect_buffer_stats(nodes)
    primary = hnsw_nodes[0]
    return {
        "node_type": primary.get("Node Type"),
        "index_name": primary.get("Index Name"),
        "relation": primary.get("Relation Name"),
        "actual_rows": primary.get("Actual Rows"),
        "planning_time_ms": root.get("Planning Time"),
        "execution_time_ms": root.get("Execution Time"),
        **buffers,
    }
