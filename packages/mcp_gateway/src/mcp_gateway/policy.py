"""Policy evaluation seam for the gateway (bitmap today, snapshot-capable later).

Authorization is the permission bitmap over the verified token. The
``PolicyEvaluator`` protocol is the single enforcement point so a future Python
PolicySnapshot verifier can be attached without re-architecting the gateway. A
policy authority that is configured but cannot decide must deny, never allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from mcp_gateway.errors import PolicyUnavailableError
from mcp_gateway.principal import GatewayPrincipal
from mcp_gateway.registry import ToolSpec
from mcp_gateway.scopes import scope_granted


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Outcome of a policy evaluation; deny is the default when unset."""

    decision: PolicyDecision
    reason: str
    scope_satisfied: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


class PolicyEvaluator(Protocol):
    """Transport-agnostic policy seam. Implementations must fail closed."""

    async def evaluate(self, principal: GatewayPrincipal, spec: ToolSpec) -> PolicyResult: ...


class BitmapPolicyEvaluator:
    """Authorize by the caller's permission bitmap; deny by default."""

    async def evaluate(  # NOSONAR python:S7503 - async contract for a future policy store
        self, principal: GatewayPrincipal, spec: ToolSpec
    ) -> PolicyResult:
        if spec.role != "read_only":  # defense in depth; registry already enforces this
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="non-read-only tool cannot be authorized",
                scope_satisfied=False,
            )
        if scope_granted(principal.permissions, spec.scope):
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                reason=f"scope {spec.scope.value} satisfied",
                scope_satisfied=True,
            )
        return PolicyResult(
            decision=PolicyDecision.DENY,
            reason=f"missing required scope {spec.scope.value}",
            scope_satisfied=False,
        )


def unavailable(reason: str) -> PolicyUnavailableError:
    """Helper for evaluators that cannot reach their authority."""
    return PolicyUnavailableError(reason)
