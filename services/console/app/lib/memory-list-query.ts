import {
  MEMORY_CATEGORIES,
  MEMORY_SOURCES,
  MEMORY_STATUSES,
  MEMORY_VISIBILITIES,
  emptyMemoryFilters,
  type MemoryCategory,
  type MemoryConfidenceBand,
  type MemoryFilterState,
  type MemoryRetrievalFilter,
  type MemorySafetyFlag,
  type MemorySource,
  type MemoryStatus,
  type MemoryValidity,
  type MemoryVisibility,
} from "./memory-preview"

export const MEMORY_VIEWS = ["all", "review", "conflicts", "pinned", "never", "expiring", "tombstoned"] as const
export const MEMORY_SORT_KEYS = [
  "updated",
  "content",
  "type",
  "agent",
  "confidence",
  "usefulness",
  "retrieved",
  "retrievals",
  "validity",
] as const
export const MEMORY_CONFIDENCE_BANDS = ["high", "medium", "low"] as const
export const MEMORY_SAFETY_FLAGS = ["pii", "injection", "conflict"] as const
export const MEMORY_VALIDITIES = ["open", "expiring", "expired"] as const
export const MEMORY_RETRIEVAL_FILTERS = ["never", "24h", "7d", "frequent"] as const
export const MEMORY_GROUP_KEYS = ["none", "agent", "category", "lifecycle", "scope"] as const
export const MEMORY_DENSITIES = ["comfortable", "compact"] as const
export const MEMORY_OPTIONAL_COLUMNS = [
  "source",
  "lineage",
  "validity",
  "memoryId",
  "agentId",
  "sessionId",
  "visibility",
] as const

export type MemoryView = (typeof MEMORY_VIEWS)[number]
export type MemorySortKey = (typeof MEMORY_SORT_KEYS)[number]
export type MemorySortDirection = "asc" | "desc"
export type MemoryGroupKey = (typeof MEMORY_GROUP_KEYS)[number]
export type MemoryDensity = (typeof MEMORY_DENSITIES)[number]
export type MemoryOptionalColumn = (typeof MEMORY_OPTIONAL_COLUMNS)[number]

export type MemoryListState = {
  search: string
  view: MemoryView
  filters: MemoryFilterState
  sort: MemorySortKey
  direction: MemorySortDirection
  group: MemoryGroupKey
  density: MemoryDensity
  columns: MemoryOptionalColumn[]
  showTags: boolean
}

export const MEMORY_SORT_LABELS: Record<MemorySortKey, string> = {
  updated: "Updated",
  content: "Memory",
  type: "Category",
  agent: "Agent",
  confidence: "Confidence",
  usefulness: "Usefulness",
  retrieved: "Last retrieved",
  retrievals: "Retrievals",
  validity: "Valid until",
}

export const MEMORY_GROUP_LABELS: Record<MemoryGroupKey, string> = {
  none: "None",
  agent: "Agent",
  category: "Category",
  lifecycle: "Lifecycle",
  scope: "Scope",
}

export const MEMORY_OPTIONAL_COLUMN_LABELS: Record<MemoryOptionalColumn, string> = {
  source: "Source",
  lineage: "Lineage",
  validity: "Valid until",
  memoryId: "Memory ID",
  agentId: "Agent ID",
  sessionId: "Session ID",
  visibility: "Scope",
}

export const MEMORY_DEFAULT_SORT_DIRECTION: Record<MemorySortKey, MemorySortDirection> = {
  updated: "desc",
  content: "asc",
  type: "asc",
  agent: "asc",
  confidence: "desc",
  usefulness: "desc",
  retrieved: "desc",
  retrievals: "desc",
  validity: "asc",
}

export function emptyMemoryListState(): MemoryListState {
  return {
    search: "",
    view: "all",
    filters: emptyMemoryFilters(),
    sort: "updated",
    direction: "desc",
    group: "none",
    density: "comfortable",
    columns: [],
    showTags: true,
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
    .slice(0, 30)
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

function allowedList<T extends string>(value: unknown, options: readonly T[]): T[] {
  return [...new Set(listValues(value).filter((entry): entry is T => allowed(entry, options)))]
}

export function parseMemoryListQuery(query: Record<string, unknown>): MemoryListState {
  const state = emptyMemoryListState()
  state.search = firstValue(query.q).trim().slice(0, 200)
  const view = firstValue(query.view)
  if (allowed(view, MEMORY_VIEWS)) state.view = view
  state.filters.categories = allowedList<MemoryCategory>(query.category, MEMORY_CATEGORIES)
  state.filters.statuses = allowedList<MemoryStatus>(query.status, MEMORY_STATUSES)
  state.filters.visibilities = allowedList<MemoryVisibility>(query.visibility, MEMORY_VISIBILITIES)
  state.filters.sources = allowedList<MemorySource>(query.source, MEMORY_SOURCES)
  state.filters.agent = firstValue(query.agent).slice(0, 120)
  const confidence = firstValue(query.confidence)
  if (allowed(confidence, MEMORY_CONFIDENCE_BANDS)) state.filters.confidence = confidence as MemoryConfidenceBand
  state.filters.safety = allowedList<MemorySafetyFlag>(query.safety, MEMORY_SAFETY_FLAGS)
  const validity = firstValue(query.validity)
  if (allowed(validity, MEMORY_VALIDITIES)) state.filters.validity = validity as MemoryValidity
  state.filters.tags = [...new Set(listValues(query.tag))].slice(0, 20)
  const retrieval = firstValue(query.retrieved)
  if (allowed(retrieval, MEMORY_RETRIEVAL_FILTERS)) state.filters.retrieval = retrieval as MemoryRetrievalFilter
  const sort = firstValue(query.sort)
  if (allowed(sort, MEMORY_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  if (direction === "asc" || direction === "desc") state.direction = direction
  const group = firstValue(query.group)
  if (allowed(group, MEMORY_GROUP_KEYS)) state.group = group
  const density = firstValue(query.density)
  if (allowed(density, MEMORY_DENSITIES)) state.density = density
  state.columns = allowedList<MemoryOptionalColumn>(query.cols, MEMORY_OPTIONAL_COLUMNS)
  state.showTags = firstValue(query.tags) !== "0"
  return state
}

export function serializeMemoryListQuery(state: MemoryListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 200))
  if (state.view !== "all") query.set("view", state.view)
  if (state.filters.categories.length) query.set("category", state.filters.categories.join(","))
  if (state.filters.statuses.length) query.set("status", state.filters.statuses.join(","))
  if (state.filters.visibilities.length) query.set("visibility", state.filters.visibilities.join(","))
  if (state.filters.sources.length) query.set("source", state.filters.sources.join(","))
  if (state.filters.agent) query.set("agent", state.filters.agent.slice(0, 120))
  if (state.filters.confidence) query.set("confidence", state.filters.confidence)
  if (state.filters.safety.length) query.set("safety", state.filters.safety.join(","))
  if (state.filters.validity) query.set("validity", state.filters.validity)
  if (state.filters.tags.length) query.set("tag", state.filters.tags.join(","))
  if (state.filters.retrieval) query.set("retrieved", state.filters.retrieval)
  if (state.sort !== "updated") query.set("sort", state.sort)
  if (state.direction !== "desc") query.set("dir", state.direction)
  if (state.group !== "none") query.set("group", state.group)
  if (state.density !== "comfortable") query.set("density", state.density)
  if (state.columns.length) query.set("cols", state.columns.join(","))
  if (!state.showTags) query.set("tags", "0")
  return query
}

export function memoryListHref(state: MemoryListState): string {
  const query = serializeMemoryListQuery(state).toString()
  return query ? `/memories?${query}` : "/memories"
}

export function memoryDetailHref(id: string, returnTo: string): string {
  return `/memories/${encodeURIComponent(id)}?return=${encodeURIComponent(returnTo)}`
}
