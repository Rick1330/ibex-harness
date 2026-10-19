"""Request-scoped, token-derived identity for the gateway.

The caller can never supply ``org_id`` or agent identity; every field here is
bound from the AuthService-validated token. Tool input schemas reject unknown
arguments (``additionalProperties: false``), so an identity argument cannot even
reach the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GatewayPrincipal:
    """Verified principal. ``org_id`` is the sole tenant authority for reads."""

    org_id: UUID
    permissions: int
    agent_id: UUID | None = None
    principal_id: str | None = None
    token_id: str | None = None
