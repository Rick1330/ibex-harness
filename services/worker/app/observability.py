"""Observability hooks for Celery tasks (m3.5.A.2).

OTel span wrapping, ``task_failure`` dead-letter handling, and Prometheus counters
land here in milestone 3.5.A.2. This module is intentionally empty for A.1 so
signal handlers can attach without changing task signatures.

**A.1 exception (m3.5.A.1 milestone):** MONITORING.md worker metrics
(``ibex_worker_tasks_total``, queue depth, DLQ counters) are deferred to A.2;
the empty ``__all__`` stub is the approved seam until then.
"""

__all__: list[str] = []
