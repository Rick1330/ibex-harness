"""FastAPI dependency providers."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.errors import AuthenticationError
from app.state import AppState

_bearer = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
BearerCredDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_embedder_state(request: Request) -> AppState:
    return request.app.state.embedder


def _bearer_token_matches(provided: str, expected: str) -> bool:
    if not expected:
        return False
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


def require_service_auth(
    credentials: BearerCredDep,
    settings: SettingsDep,
) -> None:
    expected = settings.api_token.get_secret_value() if settings.api_token is not None else ""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("missing Bearer token")
    if not _bearer_token_matches(credentials.credentials, expected):
        raise AuthenticationError("invalid Bearer token")


AppStateDep = Annotated[AppState, Depends(get_embedder_state)]
ServiceAuthDep = Annotated[None, Depends(require_service_auth)]
