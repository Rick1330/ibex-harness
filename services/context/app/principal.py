"""Verified principal binding for AssembleContext (ADR-0096).

``PrincipalContext`` is caller-asserted and **unsigned**. The checks here are
consistency checks, not authentication: the service token (``app.grpc_auth``)
authenticates the caller, and per-user authorization stays at the proxy.

What this module guarantees once a request reaches the assembler:

* the principal is present and internally consistent (authority, canonical
  UUIDs, bounded ``principal_id``, a fresh ``issued_at``, a non-stale
  ``expires_at``);
* the request's ``org_id`` / ``agent_id`` selectors are byte-identical to the
  verified principal, so a caller cannot steer retrieval into another tenant;
* the domain request is built from the principal, never from the selectors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final
from uuid import UUID

AUTHORITY_AUTH_SERVICE: Final[str] = "AuthService"
MAX_PRINCIPAL_SKEW_SECONDS: Final[float] = 30.0
MAX_PRINCIPAL_ID_CHARS: Final[int] = 256
MAX_CORRELATION_CHARS: Final[int] = 128


class PrincipalError(Exception):
    """Base class for principal rejection (typed per reason)."""

    reason: str = "invalid"


class PrincipalMissing(PrincipalError):
    """``principal_context`` was not supplied with the request."""

    reason = "missing"


class PrincipalInvalid(PrincipalError):
    """The principal is malformed or stale (bad authority/UUIDs/timestamps)."""

    reason = "invalid"


class PrincipalMismatch(PrincipalError):
    """The request selectors disagree with the verified principal."""

    reason = "mismatch"


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    """Canonical identity the assembler is allowed to act on."""

    org_id: UUID
    agent_id: UUID
    request_id: str = ""
    trace_id: str = ""


def verify_principal(request: object, *, now: float | None = None) -> VerifiedPrincipal:
    """Validate ``request.principal_context`` and return canonical identity."""
    principal = _principal_message(request)
    _require_authority(principal)
    org_id = _canonical_uuid(_text_field(principal, "org_id"), label="org_id")
    agent_id = _canonical_uuid(_text_field(principal, "agent_id"), label="agent_id")
    _require_principal_id(_text_field(principal, "principal_id"))
    current = time.time() if now is None else now
    _require_issued_at(principal, current)
    _require_not_expired(principal, current)
    return VerifiedPrincipal(
        org_id=org_id,
        agent_id=agent_id,
        request_id=_correlation(_text_field(principal, "request_id")),
        trace_id=_correlation(_text_field(principal, "trace_id")),
    )


def bind_selectors(request: object, verified: VerifiedPrincipal) -> None:
    """Require the request selectors to equal the verified principal exactly."""
    expected_org = str(verified.org_id)
    expected_agent = str(verified.agent_id)
    if _text_field(request, "org_id") != expected_org:
        raise PrincipalMismatch("request org_id does not match verified principal")
    if _text_field(request, "agent_id") != expected_agent:
        raise PrincipalMismatch("request agent_id does not match verified principal")


def _principal_message(request: object) -> object:
    holder = getattr(request, "principal_context", None)
    if holder is None or not _has_field(request, "principal_context"):
        raise PrincipalMissing("principal_context is required")
    return holder


def _has_field(message: object, name: str) -> bool:
    """``HasField`` when the message is protobuf; absent means "assume present"."""
    has_field = getattr(message, "HasField", None)
    if has_field is None:
        return True
    try:
        return bool(has_field(name))
    except (ValueError, KeyError):  # non-optional scalar: presence is undefined
        return True


def _require_authority(principal: object) -> None:
    authority = _text_field(principal, "authority")
    if authority != AUTHORITY_AUTH_SERVICE:
        raise PrincipalInvalid("principal authority must be AuthService")


def _require_issued_at(principal: object, current: float) -> None:
    issued_at = _timestamp_seconds(principal, "issued_at")
    if issued_at is None:
        raise PrincipalInvalid("issued_at is required")
    if abs(current - issued_at) > MAX_PRINCIPAL_SKEW_SECONDS:
        raise PrincipalInvalid("issued_at is outside the +/-30s window")


def _require_not_expired(principal: object, current: float) -> None:
    expires_at = _timestamp_seconds(principal, "expires_at")
    if expires_at is not None and current - expires_at > MAX_PRINCIPAL_SKEW_SECONDS:
        raise PrincipalInvalid("principal context is expired")


def _require_principal_id(principal_id: str) -> None:
    if not principal_id or principal_id != principal_id.strip():
        raise PrincipalInvalid("principal_id must be a bounded non-empty string")
    if len(principal_id) > MAX_PRINCIPAL_ID_CHARS:
        raise PrincipalInvalid("principal_id must be a bounded non-empty string")


def _canonical_uuid(raw: str, *, label: str) -> UUID:
    try:
        parsed = UUID(raw)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PrincipalInvalid(f"{label} must be a canonical UUID") from exc
    if str(parsed) != raw:
        raise PrincipalInvalid(f"{label} must be a canonical lowercase UUID")
    return parsed


def _timestamp_seconds(message: object, name: str) -> float | None:
    if not _has_field(message, name):
        return None
    holder = getattr(message, name, None)
    if holder is None:
        return None
    return _holder_seconds(holder, name=name)


def _holder_seconds(holder: object, *, name: str) -> float:
    """Coerce a proto ``Timestamp`` (or a bare number in tests) to seconds."""
    seconds = getattr(holder, "seconds", None)
    if seconds is None:
        if _is_number(holder):
            return float(holder)
        raise PrincipalInvalid(f"{name} must be a proto timestamp")
    nanos = getattr(holder, "nanos", 0) or 0
    return float(seconds) + float(nanos) / 1e9


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _correlation(raw: str) -> str:
    if len(raw) > MAX_CORRELATION_CHARS:
        raise PrincipalInvalid("principal correlation id exceeds 128 characters")
    return raw


def _text_field(message: object, name: str) -> str:
    value = getattr(message, name, "")
    if not isinstance(value, str):
        raise PrincipalInvalid(f"{name} must be a string")
    return value
