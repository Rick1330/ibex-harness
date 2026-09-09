"""FastAPI exception handlers → IBEX error envelope."""

from __future__ import annotations

from typing import Any

from apierror_py import (
    AUTH_UNAVAILABLE,
    INTERNAL_ERROR,
    INVALID_TOKEN,
    MISSING_TOKEN,
    NOT_FOUND,
    SERVICE_DEGRADED,
    VALIDATION_ERROR,
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


def _docs_url(settings: Settings | None, code: str) -> str | None:
    if settings is None:
        return None
    base = settings.docs_base_url.rstrip("/")
    return f"{base}/errors/{code}"


def envelope_response(
    *,
    code: str,
    message: str,
    detail: str | None = None,
    field_errors: list[FieldError] | None = None,
    settings: Settings | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    request_id = require_current()
    payload = build_envelope(
        code=code,
        message=message,
        request_id=request_id,
        detail=detail,
        docs_url=_docs_url(settings, code),
        field_errors=field_errors,
    )
    return JSONResponse(
        status_code=status_code or http_status_for_code(code),
        content=payload,
        headers={"X-Request-ID": request_id},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    return envelope_response(
        code=exc.code,
        message=exc.message,
        detail=exc.detail,
        field_errors=exc.field_errors,
        settings=settings,
    )


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
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
        detail="One or more fields failed validation",
        field_errors=field_errors,
        settings=settings,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Map Starlette/FastAPI HTTPException into the IBEX envelope when possible."""
    settings = getattr(request.app.state, "settings", None)
    detail: Any = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        code = str(detail["code"])
        message = str(detail["message"])
        return envelope_response(
            code=code,
            message=message,
            settings=settings,
            status_code=exc.status_code,
        )
    code = INTERNAL_ERROR if exc.status_code >= 500 else VALIDATION_ERROR
    if exc.status_code == 401:
        code = INVALID_TOKEN
    elif exc.status_code == 404:
        code = NOT_FOUND
    elif exc.status_code == 503:
        code = SERVICE_DEGRADED
    message = detail if isinstance(detail, str) else str(detail)
    return envelope_response(
        code=code,
        message=message,
        settings=settings,
        status_code=exc.status_code,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    settings = getattr(request.app.state, "settings", None)
    return envelope_response(
        code=INTERNAL_ERROR,
        message="An unexpected error occurred",
        detail=type(exc).__name__,
        settings=settings,
    )


def auth_failed_response(message: str, settings: Settings | None) -> JSONResponse:
    code = MISSING_TOKEN if "missing" in message.lower() else INVALID_TOKEN
    return envelope_response(code=code, message=message, settings=settings)


def auth_unavailable_response(settings: Settings | None) -> JSONResponse:
    return envelope_response(
        code=AUTH_UNAVAILABLE,
        message="Authentication unavailable",
        settings=settings,
    )
