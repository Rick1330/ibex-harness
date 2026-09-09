"""IBEX HTTP error envelope (Python)."""

from __future__ import annotations

from apierror_py.codes import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INTERNAL_ERROR,
    INVALID_TOKEN,
    MISSING_TOKEN,
    NOT_FOUND,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
)
from apierror_py.envelope import FieldError, build_envelope, http_status_for_code

__all__ = [
    "AUTH_UNAVAILABLE",
    "INSUFFICIENT_PERMISSIONS",
    "INTERNAL_ERROR",
    "INVALID_TOKEN",
    "MISSING_TOKEN",
    "NOT_FOUND",
    "SERVICE_DEGRADED",
    "VALIDATION_ERROR",
    "FieldError",
    "build_envelope",
    "http_status_for_code",
]
