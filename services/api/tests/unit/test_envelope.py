"""Envelope builder smoke via package import from app context."""

from __future__ import annotations

from apierror_py import VALIDATION_ERROR, FieldError, build_envelope


def test_envelope_shape_matches_docs() -> None:
    payload = build_envelope(
        code=VALIDATION_ERROR,
        message="Request validation failed",
        request_id="00000000-0000-4000-8000-000000000099",
        detail="fields",
        field_errors=[FieldError(field="q", code="INVALID", message="bad")],
    )
    err = payload["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Request validation failed"
    assert err["request_id"] == "00000000-0000-4000-8000-000000000099"
    assert isinstance(err["timestamp"], str)
    assert err["field_errors"][0]["field"] == "q"
