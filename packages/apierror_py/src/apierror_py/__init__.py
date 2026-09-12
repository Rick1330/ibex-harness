"""IBEX HTTP error envelope (Python)."""

from __future__ import annotations

from apierror_py.codes import (
    AGENT_HAS_SESSIONS,
    AGENT_SLUG_CONFLICT,
    AGENT_STATUS_CONFLICT,
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INTERNAL_ERROR,
    PERMISSION_ELEVATION_DENIED,
    INVALID_TOKEN,
    INVALID_CREDENTIAL,
    LAST_OWNER_PROTECTED,
    MISSING_TOKEN,
    MODEL_POLICY_PATTERN_CONFLICT,
    NOT_FOUND,
    ORG_SUSPENDED,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
)
from apierror_py.envelope import EnvelopeOpts, FieldError, build_envelope, http_status_for_code

__all__ = [
    "AGENT_HAS_SESSIONS",
    "AGENT_SLUG_CONFLICT",
    "AGENT_STATUS_CONFLICT",
    "AUTH_UNAVAILABLE",
    "INSUFFICIENT_PERMISSIONS",
    "INTERNAL_ERROR",
    "PERMISSION_ELEVATION_DENIED",
    "INVALID_TOKEN",
    "INVALID_CREDENTIAL",
    "LAST_OWNER_PROTECTED",
    "MISSING_TOKEN",
    "MODEL_POLICY_PATTERN_CONFLICT",
    "NOT_FOUND",
    "ORG_SUSPENDED",
    "SERVICE_DEGRADED",
    "VALIDATION_ERROR",
    "EnvelopeOpts",
    "FieldError",
    "build_envelope",
    "http_status_for_code",
]
