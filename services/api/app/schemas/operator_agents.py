"""Public operator agent read models.

The operator projection deliberately omits ``org_id``, ``config``, and
``metadata``: the browser does not need tenant authority or free-form
configuration to render the agent lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agents import AgentResponse, AgentStatus


class OperatorAgent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None = None
    status: AgentStatus
    default_provider: str | None = None
    default_model: str | None = None
    tags: list[str] = Field(default_factory=list)
    total_sessions: int = 0
    total_memories: int = 0
    total_tokens_used: int = 0
    last_active_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_agent(cls, agent: AgentResponse) -> OperatorAgent:
        return cls.model_validate(agent)
