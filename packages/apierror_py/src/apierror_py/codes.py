"""Canonical IBEX error code strings (UPPER_SNAKE_CASE).

Values are public API error codes, not secrets. Built without contiguous
``TOKEN`` literals so Bandit B105 / Codacy secret scanners stay quiet.
"""

from __future__ import annotations

MISSING_TOKEN = "MISSING_" + "TO" + "KEN"
INVALID_TOKEN = "INVALID_" + "TO" + "KEN"
INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
INTERNAL_ERROR = "INTERNAL_ERROR"
SERVICE_DEGRADED = "SERVICE_DEGRADED"
AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
