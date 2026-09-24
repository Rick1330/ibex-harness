/**
 * Client for /v1/agents* — backed by in-memory fixtures that mirror the
 * shipped 4.A.3 handlers (status transitions, 409 AGENT_HAS_SESSIONS, etc.).
 */

import { AGENT_STORE, toListItem } from "./fixtures"
import type {
  AgentConfig,
  AgentDetail,
  AgentListParams,
  AgentListResponse,
  AgentStatus,
  ApiError,
  PauseResponse,
} from "./types"

function delay(ms = 180) {
  return new Promise((r) => window.setTimeout(r, ms))
}

function findIndex(id: string) {
  return AGENT_STORE.findIndex((a) => a.agent_id === id)
}

function clone<T>(v: T): T {
  return structuredClone(v)
}

export class AgentApiError extends Error {
  status: number
  code: string
  constructor(err: ApiError) {
    super(err.message)
    this.status = err.status
    this.code = err.code
  }
}

export async function listAgents(
  params: AgentListParams = {},
): Promise<AgentListResponse> {
  await delay()
  const limit = params.limit ?? 20
  let rows = AGENT_STORE.map(toListItem)

  if (params.status && params.status !== "all") {
    rows = rows.filter((r) => r.status === params.status)
  }
  if (params.tags?.length) {
    rows = rows.filter((r) => params.tags!.every((t) => r.tags.includes(t)))
  }
  if (params.search?.trim()) {
    const q = params.search.trim().toLowerCase()
    rows = rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.slug.toLowerCase().includes(q) ||
        (r.description?.toLowerCase().includes(q) ?? false),
    )
  }

  const total_count = rows.length
  let start = 0
  if (params.cursor) {
    const idx = rows.findIndex((r) => r.agent_id === params.cursor)
    start = idx >= 0 ? idx + 1 : 0
  }
  const slice = rows.slice(start, start + limit)
  const last = slice[slice.length - 1]
  const has_more = start + limit < total_count

  return {
    items: slice,
    next_cursor: has_more && last ? last.agent_id : null,
    has_more,
    total_count,
  }
}

/** POST /v1/agents — 4.A.3 create. Slug must match agents_slug_format. */
export async function createAgent(input: {
  name: string
  slug: string
  description?: string | null
  tags?: string[]
  org_id?: string
}): Promise<AgentDetail> {
  await delay(260)
  const slug = input.slug.trim().toLowerCase()
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
    throw new AgentApiError({
      status: 400,
      code: "INVALID_SLUG",
      message: "Slug must match ^[a-z0-9-]+$ (agents_slug_format)",
    })
  }
  if (
    AGENT_STORE.some((a) => a.slug === slug && !a.agent_id.startsWith("del_"))
  ) {
    throw new AgentApiError({
      status: 409,
      code: "SLUG_TAKEN",
      message: "An agent with this slug already exists in the org",
    })
  }
  const now = new Date().toISOString()
  const row: AgentDetail = {
    agent_id: `agt_${Math.random().toString(36).slice(2, 12)}`,
    org_id: input.org_id ?? "org_acme",
    name: input.name.trim(),
    slug,
    description: input.description ?? null,
    status: "active",
    tags: input.tags ?? [],
    total_sessions: 0,
    total_memories: 0,
    total_tokens_used: 0,
    last_active_at: null,
    active_directive_version_id: null,
    active_directive_version: null,
    active_directive_hash: null,
    default_provider: null,
    default_model: null,
    created_at: now,
    updated_at: now,
    active_session_count: 0,
    config: {
      memory_extraction_enabled: true,
      memory_scope: "agent",
      max_memories_per_context: 12,
      context_budget_tokens: 8000,
      drift_detection_enabled: true,
      drift_sensitivity: 0.35,
      loop_detection_threshold: 3,
      heartbeat_interval_seconds: 30,
      llm_providers: [],
      default_provider: null,
      default_model: null,
    },
  }
  AGENT_STORE.unshift(row)
  return clone(row)
}

/** Active (non-deleted) agent count for org — onboarding trigger. */
export async function countOrgAgents(orgId: string): Promise<number> {
  await delay(80)
  return AGENT_STORE.filter((a) => a.org_id === orgId).length
}

export async function getAgent(agentId: string): Promise<AgentDetail> {
  await delay()
  const row = AGENT_STORE.find((a) => a.agent_id === agentId)
  // Identical 404 for missing vs cross-tenant — never leak existence.
  if (!row || row.org_id !== "org_acme") {
    throw new AgentApiError({
      status: 404,
      code: "NOT_FOUND",
      message: "Agent not found",
    })
  }
  return clone(row)
}

export async function patchAgent(
  agentId: string,
  body: {
    name?: string
    description?: string | null
    config?: Partial<AgentConfig>
  },
): Promise<AgentDetail> {
  await delay(220)
  const i = findIndex(agentId)
  if (i < 0) {
    throw new AgentApiError({
      status: 404,
      code: "NOT_FOUND",
      message: "Agent not found",
    })
  }
  const current = AGENT_STORE[i]
  AGENT_STORE[i] = {
    ...current,
    name: body.name ?? current.name,
    description:
      body.description !== undefined ? body.description : current.description,
    config: body.config
      ? { ...current.config, ...body.config }
      : current.config,
    default_provider:
      body.config?.default_provider !== undefined
        ? body.config.default_provider
        : current.default_provider,
    default_model:
      body.config?.default_model !== undefined
        ? body.config.default_model
        : current.default_model,
    updated_at: new Date().toISOString(),
  }
  return clone(AGENT_STORE[i])
}

async function transition(
  agentId: string,
  to: AgentStatus,
): Promise<AgentDetail> {
  await delay(200)
  const i = findIndex(agentId)
  if (i < 0) {
    throw new AgentApiError({
      status: 404,
      code: "NOT_FOUND",
      message: "Agent not found",
    })
  }
  AGENT_STORE[i] = {
    ...AGENT_STORE[i],
    status: to,
    updated_at: new Date().toISOString(),
  }
  return clone(AGENT_STORE[i])
}

export async function activateAgent(agentId: string) {
  return transition(agentId, "active")
}

export async function pauseAgent(agentId: string): Promise<PauseResponse> {
  const agent = await transition(agentId, "paused")
  const n = agent.active_session_count
  return {
    agent,
    active_sessions_completing: n,
    message:
      n > 0
        ? `${n} active session${n === 1 ? "" : "s"} will complete normally.`
        : "Agent paused. No active sessions in flight.",
  }
}

export async function archiveAgent(agentId: string) {
  return transition(agentId, "archived")
}

export async function deleteAgent(agentId: string): Promise<void> {
  await delay(200)
  const i = findIndex(agentId)
  if (i < 0) {
    throw new AgentApiError({
      status: 404,
      code: "NOT_FOUND",
      message: "Agent not found",
    })
  }
  if (AGENT_STORE[i].total_sessions > 0) {
    throw new AgentApiError({
      status: 409,
      code: "AGENT_HAS_SESSIONS",
      message: `Cannot delete agent with ${AGENT_STORE[i].total_sessions} sessions. Archive instead, or wait until sessions are purged.`,
    })
  }
  AGENT_STORE.splice(i, 1)
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M tokens`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K tokens`
  return `${n} tokens`
}

export function formatCompact(n: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(n)
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "never"
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return "—"
  // Stable relative labels for fixtures (avoid Date.now hydration drift in lists)
  const known: Record<string, string> = {
    "2026-02-11T14:20:00.000Z": "2m ago",
    "2026-02-11T14:10:00.000Z": "12m ago",
    "2026-02-11T12:00:00.000Z": "2h ago",
    "2026-01-20T09:00:00.000Z": "22d ago",
    "2025-11-01T09:00:00.000Z": "3mo ago",
  }
  return known[iso] ?? "recently"
}
