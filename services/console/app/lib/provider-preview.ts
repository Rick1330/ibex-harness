/**
 * Illustrative provider fixtures for Connect › Providers.
 *
 * Provider manifests, model capabilities, and credential rotation are not
 * connected to a live operator read model. Every value is a design fixture and
 * the page says so in the header and the About popover.
 */

export type ProviderHealth = "healthy" | "degraded" | "down"
export type ProviderRole = "primary" | "fallback" | "secondary" | "self-hosted" | "standby"
export type CredentialState = "ok" | "due" | "overdue" | "revoked"
export type ProviderTab = "providers" | "models" | "credentials"
export type ProviderSortKey = "name" | "health" | "models" | "rotation"
export type ProviderSortDirection = "asc" | "desc"
export type ModelSource = "verified" | "declared"

export type ProviderModel = {
  id: string
  label: string
  providerId: string
  provider: string
  contextWindow: number
  caps: { tools: boolean; streaming: boolean; vision: boolean; json: boolean }
  source: ModelSource
}

export type Provider = {
  id: string
  name: string
  endpoint: string
  auth: string
  region: string
  health: ProviderHealth
  healthNote: string | null
  role: ProviderRole
  weightPct: number
  fallback: string | null
  limits: { rpm: number; tpm: number; streams: number; quota: "daily" | "monthly" | "none" }
  credential: {
    prefix: string
    scope: string
    rotatedAt: string
    dueAt: string
    state: CredentialState
    rotatedBy: string
  }
}

export type ProviderListState = {
  search: string
  tab: ProviderTab
  healths: ProviderHealth[]
  regions: string[]
  sort: ProviderSortKey
  direction: ProviderSortDirection
  provider: string
}

export const PROVIDER_TABS: { id: ProviderTab; label: string }[] = [
  { id: "providers", label: "Providers" },
  { id: "models", label: "Models" },
  { id: "credentials", label: "Credentials" },
]

export const PROVIDER_HEALTHS: ProviderHealth[] = ["healthy", "degraded", "down"]
export const PROVIDER_SORT_KEYS: ProviderSortKey[] = ["name", "health", "models", "rotation"]

export const PROVIDER_HEALTH_LABELS: Record<ProviderHealth, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
}

export const PROVIDER_ROLE_LABELS: Record<ProviderRole, string> = {
  primary: "Primary",
  fallback: "Fallback",
  secondary: "Secondary",
  "self-hosted": "Self-hosted",
  standby: "Standby",
}

export const CREDENTIAL_STATE_LABELS: Record<CredentialState, string> = {
  ok: "Current",
  due: "Due soon",
  overdue: "Overdue",
  revoked: "Revoked",
}

export const PROVIDER_SORT_LABELS: Record<ProviderSortKey, string> = {
  name: "Provider",
  health: "Health",
  models: "Models",
  rotation: "Rotation",
}

export const PROVIDER_DEFAULT_SORT_DIRECTION: Record<ProviderSortKey, ProviderSortDirection> = {
  name: "asc",
  health: "asc",
  models: "desc",
  rotation: "asc",
}

export const PROVIDER_OBSERVED_AT = "2026-10-30T15:12:00Z"

export const providers: Provider[] = [
  {
    id: "openai",
    name: "OpenAI",
    endpoint: "api.openai.com/v1",
    auth: "Bearer",
    region: "us-east",
    health: "healthy",
    healthNote: null,
    role: "primary",
    weightPct: 60,
    fallback: "anthropic",
    limits: { rpm: 10000, tpm: 2000000, streams: 500, quota: "daily" },
    credential: {
      prefix: "sk-…9f2a",
      scope: "inference",
      rotatedAt: "2026-10-18T09:20:00Z",
      dueAt: "2026-11-17T09:20:00Z",
      state: "ok",
      rotatedBy: "Mira Chen",
    },
  },
  {
    id: "anthropic",
    name: "Anthropic",
    endpoint: "api.anthropic.com/v1",
    auth: "x-api-key",
    region: "us-east",
    health: "healthy",
    healthNote: null,
    role: "fallback",
    weightPct: 25,
    fallback: "azure-openai",
    limits: { rpm: 4000, tpm: 1000000, streams: 200, quota: "daily" },
    credential: {
      prefix: "ant-…c81e",
      scope: "inference",
      rotatedAt: "2026-09-19T12:00:00Z",
      dueAt: "2026-10-19T12:00:00Z",
      state: "overdue",
      rotatedBy: "Jon Park",
    },
  },
  {
    id: "google",
    name: "Google",
    endpoint: "generativelanguage.googleapis.com",
    auth: "OAuth2",
    region: "global",
    health: "degraded",
    healthNote: "p95 latency above the warning band for 30m",
    role: "secondary",
    weightPct: 0,
    fallback: "anthropic",
    limits: { rpm: 2000, tpm: 500000, streams: 100, quota: "daily" },
    credential: {
      prefix: "oauth · …7b30",
      scope: "inference",
      rotatedAt: "2026-10-24T07:00:00Z",
      dueAt: "2026-11-23T07:00:00Z",
      state: "ok",
      rotatedBy: "Sam Ortiz",
    },
  },
  {
    id: "local-vllm",
    name: "Local vLLM",
    endpoint: "10.0.4.12:8000",
    auth: "mTLS",
    region: "self-hosted",
    health: "healthy",
    healthNote: null,
    role: "self-hosted",
    weightPct: 5,
    fallback: null,
    limits: { rpm: 600, tpm: 120000, streams: 24, quota: "none" },
    credential: {
      prefix: "mtls · …4c81",
      scope: "cluster",
      rotatedAt: "2026-10-27T06:00:00Z",
      dueAt: "2026-11-26T06:00:00Z",
      state: "ok",
      rotatedBy: "Platform",
    },
  },
  {
    id: "azure-openai",
    name: "Azure OpenAI",
    endpoint: "northstar.openai.azure.com",
    auth: "api-key",
    region: "westeurope",
    health: "healthy",
    healthNote: null,
    role: "secondary",
    weightPct: 10,
    fallback: "local-vllm",
    limits: { rpm: 8000, tpm: 1500000, streams: 400, quota: "daily" },
    credential: {
      prefix: "az-…81c0",
      scope: "inference",
      rotatedAt: "2026-10-02T10:30:00Z",
      dueAt: "2026-11-01T10:30:00Z",
      state: "due",
      rotatedBy: "Mira Chen",
    },
  },
  {
    id: "mistral",
    name: "Mistral",
    endpoint: "api.mistral.ai/v1",
    auth: "Bearer",
    region: "eu-west",
    health: "healthy",
    healthNote: null,
    role: "standby",
    weightPct: 0,
    fallback: "openai",
    limits: { rpm: 1200, tpm: 300000, streams: 60, quota: "monthly" },
    credential: {
      prefix: "mis-…a041",
      scope: "inference",
      rotatedAt: "2026-10-28T14:00:00Z",
      dueAt: "2026-11-27T14:00:00Z",
      state: "ok",
      rotatedBy: "Avery Brooks",
    },
  },
]

export const providerModels: ProviderModel[] = [
  {
    id: "gpt-4.1",
    label: "gpt-4.1",
    providerId: "openai",
    provider: "OpenAI",
    contextWindow: 1047576,
    caps: { tools: true, streaming: true, vision: true, json: true },
    source: "verified",
  },
  {
    id: "gpt-4.1-mini",
    label: "gpt-4.1-mini",
    providerId: "azure-openai",
    provider: "Azure OpenAI",
    contextWindow: 1047576,
    caps: { tools: true, streaming: true, vision: true, json: true },
    source: "verified",
  },
  {
    id: "claude-sonnet-4",
    label: "claude-sonnet-4",
    providerId: "anthropic",
    provider: "Anthropic",
    contextWindow: 200000,
    caps: { tools: true, streaming: true, vision: false, json: true },
    source: "verified",
  },
  {
    id: "gemini-2.5-pro",
    label: "gemini-2.5-pro",
    providerId: "google",
    provider: "Google",
    contextWindow: 1048576,
    caps: { tools: true, streaming: true, vision: true, json: true },
    source: "declared",
  },
  {
    id: "llama-3.3-70b",
    label: "llama-3.3-70b",
    providerId: "local-vllm",
    provider: "Local vLLM",
    contextWindow: 131072,
    caps: { tools: true, streaming: true, vision: false, json: false },
    source: "verified",
  },
  {
    id: "mistral-large-2",
    label: "mistral-large-2",
    providerId: "mistral",
    provider: "Mistral",
    contextWindow: 131072,
    caps: { tools: true, streaming: true, vision: false, json: true },
    source: "declared",
  },
]

export const PROVIDER_CAPABILITY_KEYS = [
  { key: "tools", label: "Tools" },
  { key: "streaming", label: "Streaming" },
  { key: "vision", label: "Vision" },
  { key: "json", label: "JSON" },
] as const

export function providerById(id: string): Provider | null {
  return providers.find((provider) => provider.id === id) ?? null
}

export function modelsForProvider(providerId: string): ProviderModel[] {
  return providerModels.filter((model) => model.providerId === providerId)
}

export function providerMatches(provider: Provider, state: ProviderListState): boolean {
  if (state.healths.length && !state.healths.includes(provider.health)) return false
  if (state.regions.length && !state.regions.includes(provider.region)) return false
  const search = state.search.trim().toLowerCase()
  if (!search) return true
  return [provider.id, provider.name, provider.endpoint, provider.region, provider.auth, provider.role]
    .join(" ")
    .toLowerCase()
    .includes(search)
}

export function modelMatches(model: ProviderModel, state: ProviderListState): boolean {
  const search = state.search.trim().toLowerCase()
  if (!search) return true
  return [model.id, model.label, model.provider, model.providerId, model.source]
    .join(" ")
    .toLowerCase()
    .includes(search)
}

export function credentialMatches(provider: Provider, state: ProviderListState): boolean {
  const search = state.search.trim().toLowerCase()
  if (!search) return true
  return [provider.name, provider.credential.prefix, provider.credential.scope, provider.credential.state]
    .join(" ")
    .toLowerCase()
    .includes(search)
}

export function sortProviders(rows: Provider[], key: ProviderSortKey, direction: ProviderSortDirection): Provider[] {
  const multiplier = direction === "asc" ? 1 : -1
  const healthOrder: Record<ProviderHealth, number> = { down: 0, degraded: 1, healthy: 2 }
  return [...rows].sort((left, right) => {
    switch (key) {
      case "health":
        return multiplier * (healthOrder[left.health] - healthOrder[right.health])
      case "models":
        return multiplier * (modelsForProvider(left.id).length - modelsForProvider(right.id).length)
      case "rotation":
        return multiplier * (Date.parse(left.credential.dueAt) - Date.parse(right.credential.dueAt))
      default:
        return multiplier * left.name.localeCompare(right.name)
    }
  })
}

export function providerRegions(): string[] {
  return [...new Set(providers.map((provider) => provider.region))].sort((a, b) => a.localeCompare(b))
}

export function providerSummary() {
  const degraded = providers.filter((provider) => provider.health !== "healthy")
  const rotationDue = providers.filter(
    (provider) => provider.credential.state === "overdue" || provider.credential.state === "due",
  )
  return {
    configured: providers.length,
    healthy: providers.filter((provider) => provider.health === "healthy").length,
    degraded: degraded.length,
    rotationDue: rotationDue.length,
    models: providerModels.length,
    declared: providerModels.filter((model) => model.source === "declared").length,
  }
}

export type ProviderAttention = {
  id: string
  providerId: string
  title: string
  reason: string
  detail: string
  tone: "critical" | "warning"
}

export function providerAttention(): ProviderAttention[] {
  const rows: ProviderAttention[] = []
  for (const provider of providers) {
    if (provider.credential.state === "overdue") {
      rows.push({
        id: `${provider.id}-credential`,
        providerId: provider.id,
        title: provider.name,
        reason: "Credential rotation overdue",
        detail: `${provider.credential.prefix} · last rotated ${provider.credential.rotatedAt.slice(0, 10)}`,
        tone: "critical",
      })
    } else if (provider.health === "degraded") {
      rows.push({
        id: `${provider.id}-health`,
        providerId: provider.id,
        title: provider.name,
        reason: "Provider degraded",
        detail: provider.healthNote ?? "Observed health is below the declared baseline",
        tone: "warning",
      })
    } else if (provider.credential.state === "due") {
      rows.push({
        id: `${provider.id}-due`,
        providerId: provider.id,
        title: provider.name,
        reason: "Rotation due soon",
        detail: `${provider.credential.prefix} · due ${provider.credential.dueAt.slice(0, 10)}`,
        tone: "warning",
      })
    }
  }
  return rows
}

export function emptyProviderListState(): ProviderListState {
  return {
    search: "",
    tab: "providers",
    healths: [],
    regions: [],
    sort: "name",
    direction: "asc",
    provider: "",
  }
}

function firstValue(value: unknown): string {
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.find((entry): entry is string => typeof entry === "string") ?? ""
  return ""
}

function listValues(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : [value]
  return raw
    .filter((entry): entry is string => typeof entry === "string")
    .flatMap((entry) => entry.split(","))
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

export function parseProviderQuery(query: Record<string, unknown>): ProviderListState {
  const state = emptyProviderListState()
  state.search = firstValue(query.q).trim().slice(0, 120)
  const tab = firstValue(query.tab)
  if (allowed(tab, ["providers", "models", "credentials"] as const)) state.tab = tab
  state.healths = [...new Set(listValues(query.health).filter((entry) => allowed(entry, PROVIDER_HEALTHS)))]
  state.regions = [...new Set(listValues(query.region))].slice(0, 12)
  const sort = firstValue(query.sort)
  if (allowed(sort, PROVIDER_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  state.direction = direction === "asc" || direction === "desc" ? direction : PROVIDER_DEFAULT_SORT_DIRECTION[state.sort]
  const provider = firstValue(query.provider)
  state.provider = provider && providerById(provider) ? provider : ""
  return state
}

export function serializeProviderQuery(state: ProviderListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 120))
  if (state.tab !== "providers") query.set("tab", state.tab)
  if (state.healths.length) query.set("health", state.healths.join(","))
  if (state.regions.length) query.set("region", state.regions.join(","))
  if (state.sort !== "name") query.set("sort", state.sort)
  if (state.direction !== PROVIDER_DEFAULT_SORT_DIRECTION[state.sort]) query.set("dir", state.direction)
  if (state.provider) query.set("provider", state.provider)
  return query
}

export function providerHref(state: ProviderListState, providerId?: string): string {
  const next = { ...state, provider: providerId ?? state.provider }
  const query = serializeProviderQuery(next).toString()
  return query ? `/providers?${query}` : "/providers"
}

const DAY = 24 * 60 * 60 * 1000

/** "in 18d" / "2d overdue", relative to the fixture clock. */
export function formatProviderDue(value: string): string {
  const due = Date.parse(value)
  const now = Date.parse(PROVIDER_OBSERVED_AT)
  if (!Number.isFinite(due)) return "—"
  const delta = Math.round((due - now) / DAY)
  if (delta === 0) return "today"
  if (delta > 0) return `in ${delta}d`
  return `${Math.abs(delta)}d overdue`
}

export function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`
  return String(tokens)
}
