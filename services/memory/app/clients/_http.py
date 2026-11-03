"""Shared HTTP client primitives for the embedder and reranker clients.

Both clients talk to a bearer-protected internal service with the same retry
semantics, so the auth flow and the backoff live here instead of being copied
into each client.
"""

from __future__ import annotations

import secrets
from collections.abc import Generator

import httpx

BACKOFF_BASE_SECONDS = 0.25
BACKOFF_MAX_SECONDS = 8.0


class RedactedBearerAuth(httpx.Auth):
    """Attach Authorization without putting the token in default headers/repr."""

    __slots__ = ("_token",)

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

    def __repr__(self) -> str:
        return "RedactedBearerAuth()"


def jittered_backoff(
    attempt: int,
    *,
    base_seconds: float = BACKOFF_BASE_SECONDS,
    max_seconds: float = BACKOFF_MAX_SECONDS,
) -> float:
    cap = min(base_seconds * (2**attempt), max_seconds)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


def retry_after_seconds(
    raw: str | None,
    *,
    max_seconds: float = BACKOFF_MAX_SECONDS,
) -> float | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped.isdigit():
        return None
    return min(max_seconds, float(int(stripped)))
