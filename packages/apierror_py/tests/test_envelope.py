"""Unit tests for apierror_py envelope shape."""

from __future__ import annotations

from datetime import UTC, datetime

from apierror_py import VALIDATION_ERROR, FieldError, build_envelope, http_status_for_code


def test_build_envelope_required_fields() -> None:
    fixed = datetime(2024, 1, 15, 10, 30, 45, 123000, tzinfo=UTC)
    payload = build_envelope(
        code=VALIDATION_ERROR,
        message="Request validation failed",
        request_id="0190abcd-0000-7000-8000-000000000001",
        detail="One or more fields failed validation",
        docs_url="https://docs.ibexharness.com/errors/VALIDATION_ERROR",
        field_errors=[
            FieldError(field="content", code="REQUIRED", message="content is required"),
        ],
        timestamp=fixed,
    )
    err = payload["error"]
    assert set(err.keys()) >= {
        "code",
        "message",
        "detail",
        "docs_url",
        "request_id",
        "timestamp",
        "field_errors",
    }
    assert err["code"] == "VALIDATION_ERROR"
    assert err["request_id"] == "0190abcd-0000-7000-8000-000000000001"
    assert err["timestamp"] == "2024-01-15T10:30:45.123Z"
    assert err["field_errors"][0]["field"] == "content"


def test_http_status_for_known_codes() -> None:
    assert http_status_for_code("MISSING_TOKEN") == 401
    assert http_status_for_code("NOT_FOUND") == 404
    assert http_status_for_code("AUTH_UNAVAILABLE") == 503
    assert http_status_for_code("UNKNOWN_CODE") == 500
