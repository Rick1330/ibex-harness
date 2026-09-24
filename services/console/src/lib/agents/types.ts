/**
 * Agent Management (4.A.3) — contracts mirror shipped
 * GET/POST/PATCH/DELETE /v1/agents* and ibex_core.agents.
 *
 * Stats endpoint GET /v1/agents/{id}/stats is deferred — UI must not invent it.
 */

export type AgentStatus = "active" | "paused" | "suspended" | "archived"

export type MemoryScope = "agent" | "org" | "session"

/** Real `config` JSONB shape from the agents schema. */
export type AgentConfig = {
  memory_extraction_enabled: boolean
  memory_scope: MemoryScope
  max_memories_per_context: number
  context_budget_tokens: number
  drift_detection_enabled: boolean
  drift_sensitivity: number
  loop_detection_threshold: number
  heartbeat_interval_seconds: number
  llm_providers: string[]
  default_provider: string | null
  default_model: string | null
}

export type AgentListItem = {
  agent_id: string
  name: string
  slug: string
  description: string | null
  status: AgentStatus
  tags: string[]
  total_sessions: number
  total_memories: number
  total_tokens_used: number
  last_active_at: string | null
  active_directive_version_id: string | null
  active_directive_version: number | null
  active_directive_hash: string | null
  default_provider: string | null
  default_model: string | null
  created_at: string
  updated_at: string
}

export type AgentDetail = AgentListItem & {
  org_id: string
  config: AgentConfig
  /** Active sessions that will complete after pause — returned by pause API. */
  active_session_count: number
}

export type AgentListParams = {
  status?: AgentStatus | "all"
  tags?: string[]
  search?: string
  cursor?: string | null
  limit?: number
}

export type AgentListResponse = {
  items: AgentListItem[]
  next_cursor: string | null
  has_more: boolean
  total_count: number
}

export type PauseResponse = {
  agent: AgentDetail
  message: string
  active_sessions_completing: number
}

export type ApiError = {
  status: number
  code: string
  message: string
}
