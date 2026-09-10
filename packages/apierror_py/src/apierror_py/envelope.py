"""Build the stable IBEX HTTP error envelope dict."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from apierror_py.codes import (
    AGENT_HAS_SESSIONS,
    AGENT_NOT_AUTHORIZED,
    AGENT_SLUG_CONFLICT,
    AGENT_STATUS_CONFLICT,
    AGENT_SUSPENDED,
    AUTH_UNAVAILABLE,
    IDEMPOTENCY_IN_PROGRESS,
    IDEMPOTENCY_KEY_REUSE,
    INSUFFICIENT_PERMISSIONS,
    INTERNAL_ERROR,
    PERMISSION_ELEVATION_DENIED,
    INVALID_JSON,
    INVALID_REQUEST,
    INVALID_TOKEN,
    INVALID_CREDENTIAL,
    LAST_OWNER_PROTECTED,
    METHOD_NOT_ALLOWED,
    MISSING_AGENT_ID,
    MISSING_TOKEN,
    NOT_FOUND,
    ORG_SUSPENDED,
    PAYLOAD_TOO_LARGE,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_TIMEOUT,
    PROVIDER_UNAVAILABLE,
    RATE_LIMITED,
    SERVICE_DEGRADED,
    UNSUPPORTED_MEDIA_TYPE,
    VALIDATION_ERROR,
)

_STATUS_BY_CODE: dict[str, int] = {
    MISSING_TOKEN: 401,
    INVALID_TOKEN: 401,
    INSUFFICIENT_PERMISSIONS: 403,
    PERMISSION_ELEVATION_DENIED: 403,
    INVALID_JSON: 400,
    INVALID_REQUEST: 400,
    PROVIDER_NOT_CONFIGURED: 501,
    PAYLOAD_TOO_LARGE: 413,
    UNSUPPORTED_MEDIA_TYPE: 415,
    VALIDATION_ERROR: 400,
    INVALID_CREDENTIAL: 422,
    METHOD_NOT_ALLOWED: 405,
    MISSING_AGENT_ID: 400,
    AGENT_NOT_AUTHORIZED: 403,
    AGENT_SUSPENDED: 403,
    ORG_SUSPENDED: 403,
    LAST_OWNER_PROTECTED: 409,
    AGENT_SLUG_CONFLICT: 409,
    AGENT_HAS_SESSIONS: 409,
    AGENT_STATUS_CONFLICT: 409,
    RATE_LIMITED: 429,
    IDEMPOTENCY_KEY_REUSE: 409,
    IDEMPOTENCY_IN_PROGRESS: 409,
    INTERNAL_ERROR: 500,
    SERVICE_DEGRADED: 503,
    AUTH_UNAVAILABLE: 503,
    PROVIDER_UNAVAILABLE: 503,
    PROVIDER_TIMEOUT: 504,
    NOT_FOUND: 404,
}


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class EnvelopeOpts:
    """Optional envelope fields (mirrors Go apierror.WriteOpts)."""

    detail: str | None = None
    docs_url: str | None = None
    field_errors: list[FieldError] | None = None
    timestamp: datetime | None = None


def http_status_for_code(code: str) -> int:
    return _STATUS_BY_CODE.get(code, 500)


def build_envelope(
    *,
    code: str,
    message: str,
    request_id: str,
    opts: EnvelopeOpts | None = None,
) -> dict[str, Any]:
    """Return ``{"error": {...}}`` matching API_DOCUMENTATION.md / Go apierror."""
    options = opts or EnvelopeOpts()
    ts = options.timestamp if options.timestamp is not None else datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    else:
        ts = ts.astimezone(UTC)
    # Match Go json.Marshal of time.Time (RFC3339Nano with Z).
    ts_str = ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "timestamp": ts_str,
    }
    if options.detail:
        body["detail"] = options.detail
    if options.docs_url:
        body["docs_url"] = options.docs_url
    if options.field_errors is not None:
        body["field_errors"] = [asdict(fe) for fe in options.field_errors]
    return {"error": body}
