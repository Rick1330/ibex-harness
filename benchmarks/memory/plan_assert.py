"""Assert pgvector HNSW plans from EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)."""

from __future__ import annotations

from typing import Any

_HNSW_INDEX = "idx_memories_embedding_hnsw"
_GIN_INDEX = "idx_memories_search_vector"
_NODE_TYPE = "Node Type"
_INDEX_NAME = "Index Name"
_RELATION_NAME = "Relation Name"


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

def _is_index_access(node: dict[str, Any], index_name: str) -> bool:
    ntype = str(node.get(_NODE_TYPE) or "")
    name = str(node.get(_INDEX_NAME) or "")
    return index_name in name and ("Index" in ntype or "Bitmap" in ntype)


def _is_seq_on_memories(node: dict[str, Any]) -> bool:
    ntype = str(node.get(_NODE_TYPE) or "")
    relation = str(node.get(_RELATION_NAME) or "")
    return ntype == "Seq Scan" and relation in {"memories", "ibex_core.memories"}


def _summarize_nodes(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes[:12]:
        ntype = str(node.get(_NODE_TYPE) or "")
        index_name = str(node.get(_INDEX_NAME) or "")
        relation = str(node.get(_RELATION_NAME) or "")
        if index_name:
            parts.append(f"{ntype}@{index_name}")
        elif relation:
            parts.append(f"{ntype}@{relation}")
        else:
            parts.append(ntype or "?")
    return ", ".join(parts)


def _root_plan(explain_json: list[Any] | dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    root = explain_json[0] if isinstance(explain_json, list) else explain_json
    if not isinstance(root, dict):
        raise PlanAssertionError(f"unexpected EXPLAIN root type: {type(root)!r}")
    plan = root.get("Plan")
    if not isinstance(plan, dict):
        raise PlanAssertionError("EXPLAIN JSON missing Plan")
    return root, plan


def _require_index_nodes(
    nodes: list[dict[str, Any]],
    *,
    index_name: str,
) -> list[dict[str, Any]]:
    index_nodes = [n for n in nodes if _is_index_access(n, index_name)]
    if index_nodes:
        return index_nodes
    seq_on_memories = any(_is_seq_on_memories(n) for n in nodes)
    seq_note = "; Seq Scan on memories also present" if seq_on_memories else ""
    raise PlanAssertionError(
        f"expected Index Scan / Bitmap Index Scan on {index_name}; "
        f"saw: {_summarize_nodes(nodes)}{seq_note}"
    )


def _require_hnsw_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _require_index_nodes(nodes, index_name=_HNSW_INDEX)


def _plan_summary(
    root: dict[str, Any], primary: dict[str, Any], buffers: dict[str, int]
) -> dict[str, Any]:
    return {
        "node_type": primary.get(_NODE_TYPE),
        "index_name": primary.get(_INDEX_NAME),
        "relation": primary.get(_RELATION_NAME),
        "actual_rows": primary.get("Actual Rows"),
        "planning_time_ms": root.get("Planning Time"),
        "execution_time_ms": root.get("Execution Time"),
        **buffers,
    }


def _require_gin_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _require_index_nodes(nodes, index_name=_GIN_INDEX)


def assert_gin_index_used(explain_json: list[Any] | dict[str, Any]) -> dict[str, Any]:
    """Require an Index/Bitmap Index Scan on idx_memories_search_vector."""
    root, plan = _root_plan(explain_json)
    nodes = walk_plan_nodes(plan)
    gin_nodes = _require_gin_nodes(nodes)
    return _plan_summary(root, gin_nodes[0], collect_buffer_stats(nodes))


def assert_gin_index_scanned(*, before: int, after: int) -> int:
    """Require idx_memories_search_vector idx_scan to increase after a FTS query."""
    delta = after - before
    if delta < 1:
        raise PlanAssertionError(
            f"pg_stat idx_scan did not increase on {_GIN_INDEX} "
            f"(before={before}, after={after})"
        )
    return delta


def assert_hnsw_index_scanned(*, before: int, after: int) -> int:
    """Require idx_memories_embedding_hnsw idx_scan to increase after vector search."""
    delta = after - before
    if delta < 1:
        raise PlanAssertionError(
            f"pg_stat idx_scan did not increase on {_HNSW_INDEX} "
            f"(before={before}, after={after})"
        )
    return delta


def assert_hnsw_index_used(explain_json: list[Any] | dict[str, Any]) -> dict[str, Any]:
    """Require an Index/Bitmap Index Scan on idx_memories_embedding_hnsw."""
    root, plan = _root_plan(explain_json)
    nodes = walk_plan_nodes(plan)
    hnsw_nodes = _require_hnsw_nodes(nodes)
    return _plan_summary(root, hnsw_nodes[0], collect_buffer_stats(nodes))
