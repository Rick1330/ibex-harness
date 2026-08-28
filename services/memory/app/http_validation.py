"""HTTP validation error envelope for memory API routes."""

from __future__ import annotations

from typing import Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request


def _field_path(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        if item in ("body", "query", "path", "header"):
            continue
        parts.append(str(item))
    return ".".join(parts) if parts else "request"


def validation_error_response(exc: RequestValidationError) -> JSONResponse:
    field_errors = [
        {
            "field": _field_path(tuple(err.get("loc", ()))),
            "code": str(err.get("type", "validation_error")),
            "message": str(err.get("msg", "invalid value")),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "field_errors": field_errors,
            }
        },
    )


async def request_validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return validation_error_response(exc)
