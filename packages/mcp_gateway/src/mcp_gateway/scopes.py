"""Typed scopes mapped onto the existing permission bitmap (ADR-0009).

The gateway does not invent an authorization vocabulary. Each typed scope is a
named alias over an existing ``packages/permissions`` bit, and the authorization
decision remains a plain bitmap check on the AuthService-validated token.
"""

from __future__ import annotations

from enum import Enum

from authclient.permissions import (
    BILLING_READ,
    OPERATOR_METADATA_READ,
    OPERATOR_REDACTED_READ,
    TRACE_READ,
    has_permission,
)


class Scope(str, Enum):
    """Typed scopes exposed by the read-only operator gateway."""

    OPERATOR_READ = "operator.read"
    RUNS_READ = "runs.read"
    EVIDENCE_READ = "evidence.read"
    BUDGET_READ = "budget.read"


# Scope -> required permission bit. Extending this map is an additive contract change.
SCOPE_PERMISSIONS: dict[Scope, int] = {
    Scope.OPERATOR_READ: OPERATOR_METADATA_READ,
    Scope.RUNS_READ: TRACE_READ,
    Scope.EVIDENCE_READ: OPERATOR_REDACTED_READ,
    Scope.BUDGET_READ: BILLING_READ,
}


def permission_for_scope(scope: Scope) -> int:
    """Return the permission bit that authorizes ``scope``."""
    return SCOPE_PERMISSIONS[scope]


def scope_granted(permissions: int, scope: Scope) -> bool:
    """True only when every bit required by ``scope`` is present."""
    return has_permission(permissions, permission_for_scope(scope))
