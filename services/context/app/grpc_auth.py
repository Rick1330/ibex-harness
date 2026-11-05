"""Caller authentication for the ContextAssemblyService gRPC boundary (ADR-0096).

The service token authenticates the *caller* (proxy → context assembly). It does
not authorize the asserted tenant: ``PrincipalContext`` is unsigned and the
token is a shared secret, so any token holder can still assert any principal.
Tenant isolation remains a proxy-side property (see ``app.principal``).

Wire contract (both sides must agree exactly):

* metadata key ``x-ibex-context-service-token``, exactly one entry;
* configured via ``IBEX_CONTEXT_GRPC_SERVICE_TOKEN`` (``SecretStr``);
* missing / duplicate / mismatched token → ``UNAUTHENTICATED``.

The token value is never logged and never returned to the caller: only the RPC
``method`` and a coarse ``reason`` label are recorded.
"""

from __future__ import annotations

import hmac
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
from grpc import aio as grpc_aio
from pydantic import SecretStr

SERVICE_TOKEN_METADATA_KEY = "x-ibex-context-service-token"
SERVICE_TOKEN_MIN_CHARS = 32
SERVICE_TOKEN_MAX_CHARS = 512
UNAUTHENTICATED_DETAILS = "caller authentication required"

REASON_MISSING = "missing"
REASON_DUPLICATE = "duplicate"
REASON_MISMATCH = "mismatch"
REASON_INVALID = "invalid"

_TOKEN_RE = re.compile(
    rf"^[A-Za-z0-9_-]{{{SERVICE_TOKEN_MIN_CHARS},{SERVICE_TOKEN_MAX_CHARS}}}$"
)

logger = logging.getLogger(__name__)

Handler = Callable[[Any, grpc_aio.ServicerContext], Awaitable[Any]]


def secret_value(value: SecretStr | str | None) -> str:
    """Return the plaintext behind a ``SecretStr`` (or a bare string in tests)."""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if value is None:
        return ""
    return str(value)


def validate_service_token(token: SecretStr | str | None) -> str:
    """Return the validated token, or raise ``ValueError`` without echoing it.

    Validation happens at startup and at servicer construction, never per call.
    """
    value = secret_value(token)
    if not value:
        msg = (
            "IBEX_CONTEXT_GRPC_SERVICE_TOKEN is required: ContextAssemblyService "
            "refuses to start without caller authentication (ADR-0096)"
        )
        raise ValueError(msg)
    if not _TOKEN_RE.fullmatch(value):
        msg = (
            "IBEX_CONTEXT_GRPC_SERVICE_TOKEN must be "
            f"{SERVICE_TOKEN_MIN_CHARS}-{SERVICE_TOKEN_MAX_CHARS} characters of "
            "[A-Za-z0-9_-] (ADR-0096)"
        )
        raise ValueError(msg)
    return value


def tokens_match(presented: str | None, expected: str) -> bool:
    """Constant-time comparison over UTF-8 bytes; unusable input is a mismatch."""
    if presented is None or not expected:
        return False
    try:
        return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
    except TypeError:  # defensive: non-encodable input must not bypass the check
        return False


async def require_service_token(
    context: grpc_aio.ServicerContext,
    expected_token: str,
    *,
    method: str,
) -> None:
    """Abort ``UNAUTHENTICATED`` unless the call carries exactly one valid token.

    Enforced by ``guard_handler`` for registered RPCs *and* by every servicer
    method, so direct servicer construction cannot bypass the interceptor.
    """
    reason, presented = _presented_token(context)
    if not reason and not tokens_match(presented, expected_token):
        reason = REASON_MISMATCH
    if not reason:
        return
    logger.warning(
        "context_grpc_caller_auth_rejected method=%s reason=%s",
        method,
        reason,
    )
    await context.abort(grpc.StatusCode.UNAUTHENTICATED, UNAUTHENTICATED_DETAILS)
    raise AssertionError("unreachable")  # pragma: no cover - abort always raises


def guard_handler(
    handler: Handler,
    token: SecretStr | str,
    *,
    method: str = "",
) -> Handler:
    """Wrap a unary handler so it only runs for an authenticated caller."""
    expected = validate_service_token(token)
    label = method or getattr(handler, "__name__", "rpc")

    async def _guarded(
        request: object,
        context: grpc_aio.ServicerContext,
    ) -> object:
        await require_service_token(context, expected, method=label)
        return await handler(request, context)

    return _guarded


def _presented_token(context: object) -> tuple[str, str | None]:
    """Return ``(reason, token)``; ``reason`` is empty for one in-bounds entry."""
    entries = _metadata_entries(context)
    if entries is None:
        return REASON_INVALID, None
    values = _token_values(entries)
    if not values:
        return REASON_MISSING, None
    if len(values) > 1:
        return REASON_DUPLICATE, None
    return _validated_token(values[0])


def _token_values(entries: list[tuple[object, object]]) -> list[object]:
    """Return the values filed under the service-token key, in wire order."""
    return [
        value
        for key, value in entries
        if _normalized_key(key) == SERVICE_TOKEN_METADATA_KEY
    ]


def _validated_token(value: object) -> tuple[str, str | None]:
    """Return ``("", text)`` for one in-bounds entry, else an ``invalid`` reason."""
    text = _as_text(value)
    if text is None:
        return REASON_INVALID, None
    size = _token_size(text)
    if size is None or not SERVICE_TOKEN_MIN_CHARS <= size <= SERVICE_TOKEN_MAX_CHARS:
        return REASON_INVALID, None
    return "", text


def _token_size(text: str) -> int | None:
    """Return the UTF-8 byte length, or ``None`` when the text is not encodable."""
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError:  # lone surrogates cannot match any configured token
        return None


def _metadata_entries(context: object) -> list[tuple[object, object]] | None:
    getter = getattr(context, "invocation_metadata", None)
    if getter is None:
        return None
    raw = _raw_metadata(getter)
    if raw is None:
        return None
    entries: list[tuple[object, object]] = []
    for entry in raw:
        parsed = _entry_pair(entry)
        if parsed is None:
            return None
        entries.append(parsed)
    return entries


def _raw_metadata(getter: Callable[[], object]) -> object | None:
    """Return the raw metadata sequence, or ``None`` when it cannot be read."""
    try:
        return getter() or ()
    except Exception:  # noqa: BLE001 - a context without metadata cannot authenticate
        return None


def _entry_pair(entry: object) -> tuple[object, object] | None:
    key = getattr(entry, "key", None)
    if key is not None:
        return key, getattr(entry, "value", None)
    try:
        return entry[0], entry[1]  # type: ignore[index]
    except (TypeError, IndexError, KeyError):
        return None


def _normalized_key(key: object) -> str | None:
    if isinstance(key, bytes):
        try:
            return key.decode("ascii").lower()
        except UnicodeDecodeError:
            return None
    if isinstance(key, str):
        return key.lower()
    return None


def _as_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None
