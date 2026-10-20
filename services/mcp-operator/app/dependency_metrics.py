"""Dependency-level metrics (database, Redis, auth service)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

DB_DURATION = Histogram(
    "ibex_mcp_operator_db_duration_seconds",
    "Tenant-scoped database read duration",
    ["tool"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
DB_ERRORS = Counter(
    "ibex_mcp_operator_db_errors_total",
    "Tenant-scoped database failures",
    ["tool"],
)
AUTH_DURATION = Histogram(
    "ibex_mcp_operator_auth_duration_seconds",
    "AuthService validation duration",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 1.0, 2.5),
)
AUTH_ERRORS = Counter(
    "ibex_mcp_operator_auth_errors_total",
    "AuthService validation failures",
)
REDIS_DURATION = Histogram(
    "ibex_mcp_operator_redis_duration_seconds",
    "Redis round-trip duration for the operator limiter",
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0),
)
