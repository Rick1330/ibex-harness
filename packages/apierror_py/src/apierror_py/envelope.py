"""Build the stable IBEX HTTP error envelope dict."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

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

_STATUS_BY_CODE: dict[str, int] = {
    MISSING_TOKEN: 401,
    INVALID_TOKEN: 401,
    INSUFFICIENT_PERMISSIONS: 403,
    VALIDATION_ERROR: 400,
    NOT_FOUND: 404,
    INTERNAL_ERROR: 500,
    SERVICE_DEGRADED: 503,
    AUTH_UNAVAILABLE: 503,
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
