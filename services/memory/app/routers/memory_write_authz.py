"""Agent-scope authorization for memory write and forget routes.

A memory is addressed within exactly one agent. The token decides which agents
the caller may act for: an org-scoped token may act for any agent in its
organization, while an agent-scoped token is bound to exactly one agent.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from app.auth.client import ValidateResult


def ensure_write_agent_authorized(token: ValidateResult, body_agent_id: UUID) -> None:
    """Reject an agent-scoped token that writes for a different agent.

    An org-scoped token (``agent_id is None``) may act for any agent in its
    organization, and the composite ``(agent_id, org_id)`` foreign key is the
    backstop there. An agent-scoped token is bound to exactly one agent, so a
    body ``agent_id`` that differs is a 403 before any write is attempted —
    otherwise the token could write memories for a sibling agent in the same
    organization.
    """
    if token.agent_id is not None and token.agent_id != body_agent_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AGENT_NOT_AUTHORIZED",
                "message": "Token is not authorized for the requested agent",
            },
        )


def require_agent_scope(token: ValidateResult) -> UUID:
    """Return the token's agent id, or 403 when the token is org-scoped."""
    if token.agent_id is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AGENT_SCOPE_REQUIRED", "message": "Agent-scoped token required"},
        )
    return token.agent_id
