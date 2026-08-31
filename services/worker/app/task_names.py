"""Stable Celery task names (shared by routing, tests, and future proxy enqueue)."""

TASK_EXTRACTION_NOOP = "ibex.worker.extraction.noop"
TASK_EMBEDDING_NOOP = "ibex.worker.embedding.noop"
TASK_MCP_AUDIT_NOOP = "ibex.worker.mcp_audit.noop"
TASK_MAINTENANCE_NOOP_SWEEP = "ibex.worker.maintenance.noop_sweep"
TASK_RESULT_PROBE = "ibex.worker.maintenance.result_probe"

ALL_TASK_NAMES: tuple[str, ...] = (
    TASK_EXTRACTION_NOOP,
    TASK_EMBEDDING_NOOP,
    TASK_MCP_AUDIT_NOOP,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_RESULT_PROBE,
)
