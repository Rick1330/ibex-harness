"""FastAPI exception handlers → IBEX error envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apierror_py import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INTERNAL_ERROR,
    INVALID_TOKEN,
    MISSING_TOKEN,
    NOT_FOUND,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
    EnvelopeOpts,
    FieldError,
    build_envelope,
    http_status_for_code,
)
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.reqid import require_current


class ApiError(Exception):
    """Domain error that serializes as the IBEX envelope."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        detail: str | None = None,
        field_errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.field_errors = field_errors


@dataclass(frozen=True, slots=True)
class ResponseOpts:
    """Optional fields for envelope_response (keeps CodeScene arity ≤ 4)."""

    detail: str | None = None
    field_errors: list[FieldError] | None = None
    settings: Settings | None = None
    status_code: int | None = None


def _docs_url(settings: Settings | None, code: str) -> str | None:
    if settings is None:
        return None
    base = settings.docs_base_url.rstrip("/")
    return f"{base}/errors/{code}"


def envelope_response(*, code: str, message: str, opts: ResponseOpts | None = None) -> JSONResponse:
    options = opts or ResponseOpts()
    request_id = require_current()
    payload = build_envelope(
        code=code,
        message=message,
        request_id=request_id,
        opts=EnvelopeOpts(
            detail=options.detail,
            docs_url=_docs_url(options.settings, code),
            field_errors=options.field_errors,
        ),
    )
    return JSONResponse(
        status_code=options.status_code or http_status_for_code(code),
        content=payload,
        headers={"X-Request-ID": request_id},
    )


def _settings_from(request: Request) -> Settings | None:
    return getattr(request.app.state, "settings", None)


def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return envelope_response(
        code=exc.code,
        message=exc.message,
        opts=ResponseOpts(
            detail=exc.detail,
            field_errors=exc.field_errors,
            settings=_settings_from(request),
        ),
    )


def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    field_errors = [
        FieldError(
            field=".".join(str(part) for part in err.get("loc", ())),
            code="INVALID",
            message=str(err.get("msg", "invalid")),
        )
        for err in exc.errors()
    ]
    return envelope_response(
        code=VALIDATION_ERROR,
        message="Request validation failed",
        opts=ResponseOpts(
            detail="One or more fields failed validation",
            field_errors=field_errors,
            settings=_settings_from(request),
        ),
    )


def _code_message_from_http_detail(detail: Any) -> tuple[str, str] | None:
    if not isinstance(detail, dict):
        return None
    if "code" not in detail:
        return None
    if "message" not in detail:
        return None
    return str(detail["code"]), str(detail["message"])


def _code_for_http_status(status_code: int) -> str:
    if status_code == 401:
        return INVALID_TOKEN
    if status_code == 403:
        return INSUFFICIENT_PERMISSIONS
    if status_code == 404:
        return NOT_FOUND
    if status_code == 503:
        return SERVICE_DEGRADED
    if status_code >= 500:
        return INTERNAL_ERROR
    return VALIDATION_ERROR


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Map Starlette/FastAPI HTTPException into the IBEX envelope when possible."""
    settings = _settings_from(request)
    mapped = _code_message_from_http_detail(exc.detail)
    if mapped is not None:
        code, message = mapped
        return envelope_response(
            code=code,
            message=message,
            opts=ResponseOpts(settings=settings, status_code=exc.status_code),
        )
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return envelope_response(
        code=_code_for_http_status(exc.status_code),
        message=message,
        opts=ResponseOpts(settings=settings, status_code=exc.status_code),
    )


def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return envelope_response(
        code=INTERNAL_ERROR,
        message="An unexpected error occurred",
        opts=ResponseOpts(detail=type(exc).__name__, settings=_settings_from(request)),
    )


def auth_failed_response(message: str, settings: Settings | None) -> JSONResponse:
    code = MISSING_TOKEN if "missing" in message.lower() else INVALID_TOKEN
    return envelope_response(code=code, message=message, opts=ResponseOpts(settings=settings))


def auth_unavailable_response(settings: Settings | None) -> JSONResponse:
    return envelope_response(
        code=AUTH_UNAVAILABLE,
        message="Authentication unavailable",
        opts=ResponseOpts(settings=settings),
    )
