"""IBEX HTTP error envelope (Python)."""

from __future__ import annotations

from apierror_py.codes import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INTERNAL_ERROR,
    INVALID_TOKEN,
    LAST_OWNER_PROTECTED,
    MISSING_TOKEN,
    NOT_FOUND,
    ORG_SUSPENDED,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
)
from apierror_py.envelope import EnvelopeOpts, FieldError, build_envelope, http_status_for_code

__all__ = [
    "AUTH_UNAVAILABLE",
    "INSUFFICIENT_PERMISSIONS",
    "INTERNAL_ERROR",
    "INVALID_TOKEN",
    "LAST_OWNER_PROTECTED",
    "MISSING_TOKEN",
    "NOT_FOUND",
    "ORG_SUSPENDED",
    "SERVICE_DEGRADED",
    "VALIDATION_ERROR",
    "EnvelopeOpts",
    "FieldError",
    "build_envelope",
    "http_status_for_code",
]
