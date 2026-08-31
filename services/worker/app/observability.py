"""Observability hooks for Celery tasks (m3.5.A.2).

OTel span wrapping, ``task_failure`` dead-letter handling, and Prometheus counters
land here in milestone 3.5.A.2. This module is intentionally empty for A.1 so
signal handlers can attach without changing task signatures.
"""

__all__: list[str] = []
