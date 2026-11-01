import {
  MEMORY_CATEGORIES,
  MEMORY_CATEGORY_LABELS,
  MEMORY_PREVIEW_NOW,
  MEMORY_SOURCE_LABELS,
  MEMORY_STATUS_LABELS,
  MEMORY_STATUSES,
  MEMORY_VISIBILITY_LABELS,
  MEMORY_VISIBILITIES,
  memoryConfidenceBand,
  memoryInjectionBand,
  memoryRelativeTime,
  type MemoryCategory,
  type MemoryFilterState,
  type MemorySafetyFlag,
  type MemoryStatus,
  type PreviewMemory,
} from "./memory-preview"
import type { MemoryGroupKey, MemoryListState, MemorySortKey } from "./memory-list-query"

export type MemoryFlagTone = "critical" | "warning" | "neutral"
export type MemoryFlagKind =
  | "conflict"
  | "injection"
  | "pii"
  | "expiring"
  | "expired"

export type MemoryFlag = {
  kind: MemoryFlagKind
  label: string
  title: string
  tone: MemoryFlagTone
}

export type MemorySeverity = "none" | "warning" | "critical"

export type MemoryGroup = {
  key: string
  label: string
  rows: PreviewMemory[]
}

export type MemoryFilterChip = {
  key: string
  field: string
  value: string
  next: MemoryFilterState
}

const REVIEW_INJECTION_THRESHOLD = 0.8
const RETRIEVAL_FREQUENT_THRESHOLD = 50

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 6)}…` : id
}

export function memoryShortId(id: string): string {
  return shortId(id)
}

export function memoryNeedsReview(memory: PreviewMemory): boolean {
  return (
    memory.status === "quarantined" ||
    memory.injectionRisk >= REVIEW_INJECTION_THRESHOLD ||
    memory.conflict?.state === "open"
  )
}

export function memorySeverity(memory: PreviewMemory): MemorySeverity {
  if (memory.injectionRisk >= REVIEW_INJECTION_THRESHOLD) return "critical"
  if (memory.piiDetected && !memory.piiRedacted) return "critical"
  if (memory.status === "deleted") return "critical"
  if (
    memory.status === "quarantined" ||
    memory.conflict?.state === "open" ||
    memory.piiDetected ||
    memory.validity === "expiring" ||
    memory.validity === "expired"
  ) {
    return "warning"
  }
  return "none"
}

export function memoryFlags(memory: PreviewMemory): MemoryFlag[] {
  const flags: MemoryFlag[] = []

  if (memory.conflict?.state === "open") {
    flags.push({
      kind: "conflict",
      label: "Conflict",
      title: memory.conflict.note,
      tone: "warning",
    })
  }

  const injection = memoryInjectionBand(memory.injectionRisk)
  if (injection === "high" || injection === "medium") {
    flags.push({
      kind: "injection",
      label: "Injection",
      title: "Untrusted content matched a prompt-injection pattern. The text is data, never instructions.",
      tone: injection === "high" ? "critical" : "warning",
    })
  }

  if (memory.piiDetected) {
    flags.push({
      kind: "pii",
      label: memory.piiRedacted ? "PII redacted" : "PII exposed",
      title: memory.piiRedacted
        ? "PII was detected and redacted before this preview was exposed."
        : "PII was detected and has not been redacted.",
      tone: memory.piiRedacted ? "warning" : "critical",
    })
  }

  if (memory.validity === "expiring") {
    flags.push({
      kind: "expiring",
      label: memory.validityLabel,
      title: `This memory expires at ${memory.validUntil?.replace("T", " ").replace("Z", " UTC")}.`,
      tone: "warning",
    })
  } else if (memory.validity === "expired") {
    flags.push({
      kind: "expired",
      label: memory.validityLabel,
      title: `This memory expired at ${memory.validUntil?.replace("T", " ").replace("Z", " UTC")}.`,
      tone: "critical",
    })
  }

  return flags
}

export function memoryRetrievalSummary(memory: PreviewMemory): string {
  if (memory.retrievalCount === 0) return "Never retrieved"
  return `${memory.retrievalCount} retrievals · ${memory.lastRetrievedLabel}`
}

export function memoryHasUntrustedText(memory: PreviewMemory): boolean {
  return memoryInjectionBand(memory.injectionRisk) === "high" || memoryInjectionBand(memory.injectionRisk) === "medium"
}

export function memoryAgentIndex(agentId: string): number {
  let hash = 2166136261
  for (let index = 0; index < agentId.length; index += 1) {
    hash ^= agentId.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (Math.abs(hash) % 8) + 1
}

export function memoryCategoryToken(category: MemoryCategory): string {
  return `var(--ix-cat-${category})`
}

export function memoryCategoryLabel(category: MemoryCategory): string {
  return MEMORY_CATEGORY_LABELS[category]
}

export function memoryLifecycleCounts(memories: PreviewMemory[]): Array<{ status: MemoryStatus; count: number }> {
  return MEMORY_STATUSES.map((status) => ({
    status,
    count: memories.filter((memory) => memory.status === status).length,
  }))
}

export function memoryLifecycleLabel(status: MemoryStatus): string {
  return MEMORY_STATUS_LABELS[status]
}

export function memoryMatchesQuery(memory: PreviewMemory, rawQuery: string): boolean {
  const query = rawQuery.trim().toLowerCase()
  if (!query) return true
  return [
    memory.id,
    memory.content,
    memory.agent,
    memory.agentId,
    MEMORY_CATEGORY_LABELS[memory.category],
    MEMORY_SOURCE_LABELS[memory.source],
    MEMORY_VISIBILITY_LABELS[memory.visibility],
    MEMORY_STATUS_LABELS[memory.status],
    memory.sessionId ?? "",
    ...memory.labels.map((label) => label.label),
    ...memory.tags,
  ].some((value) => value.toLowerCase().includes(query))
}

function matchesRetrieval(memory: PreviewMemory, retrieval: MemoryFilterState["retrieval"]): boolean {
  if (!retrieval) return true
  if (retrieval === "never") return memory.retrievalCount === 0
  if (retrieval === "frequent") return memory.retrievalCount >= RETRIEVAL_FREQUENT_THRESHOLD
  if (!memory.lastRetrievedAt) return false
  const age = MEMORY_PREVIEW_NOW - Date.parse(memory.lastRetrievedAt)
  if (retrieval === "24h") return age <= 86_400_000
  return age <= 7 * 86_400_000
}

export function matchesSafetyFlag(memory: PreviewMemory, flag: MemorySafetyFlag): boolean {
  if (flag === "pii") return memory.piiDetected
  if (flag === "injection") {
    const band = memoryInjectionBand(memory.injectionRisk)
    return band === "medium" || band === "high"
  }
  return memory.conflict?.state === "open"
}

export function viewMatchesMemory(view: MemoryListState["view"], memory: PreviewMemory): boolean {
  if (view === "review") return memoryNeedsReview(memory)
  if (view === "conflicts") return memory.conflict?.state === "open"
  if (view === "pinned") return memory.pinned
  if (view === "never") return memory.retrievalCount === 0
  if (view === "expiring") return memory.validity === "expiring"
  if (view === "tombstoned") return memory.status === "deleted"
  return true
}

export function filterMemories(memories: PreviewMemory[], state: MemoryListState): PreviewMemory[] {
  const filters = state.filters
  return memories.filter((memory) => {
    if (!viewMatchesMemory(state.view, memory)) return false
    if (!memoryMatchesQuery(memory, state.search)) return false
    if (filters.categories.length && !memory.labels.some((label) => filters.categories.includes(label.label))) return false
    if (filters.statuses.length && !filters.statuses.includes(memory.status)) return false
    if (filters.visibilities.length && !filters.visibilities.includes(memory.visibility)) return false
    if (filters.sources.length && !filters.sources.includes(memory.source)) return false
    if (filters.agent && memory.agent !== filters.agent) return false
    if (filters.confidence && memoryConfidenceBand(memory.confidence) !== filters.confidence) return false
    if (filters.safety.length && !filters.safety.some((flag) => matchesSafetyFlag(memory, flag))) return false
    if (filters.validity && memory.validity !== filters.validity) return false
    if (filters.tags.length && !filters.tags.some((tag) => memory.tags.includes(tag))) return false
    if (!matchesRetrieval(memory, filters.retrieval)) return false
    return true
  })
}

function sortValue(memory: PreviewMemory, key: MemorySortKey): number | string {
  switch (key) {
    case "updated":
      return Date.parse(memory.updatedAt)
    case "content":
      return memory.content
    case "type":
      return MEMORY_CATEGORY_LABELS[memory.category]
    case "agent":
      return memory.agent
    case "confidence":
      return memory.confidence
    case "usefulness":
      return memory.usefulness
    case "retrieved":
      return memory.lastRetrievedAt ? Date.parse(memory.lastRetrievedAt) : 0
    case "retrievals":
      return memory.retrievalCount
    case "validity":
      return memory.validUntil ? Date.parse(memory.validUntil) : Number.MAX_SAFE_INTEGER
  }
}

export function sortMemories(
  memories: PreviewMemory[],
  sort: MemorySortKey,
  direction: MemoryListState["direction"],
): PreviewMemory[] {
  return [...memories].sort((first, second) => {
    const firstValue = sortValue(first, sort)
    const secondValue = sortValue(second, sort)
    const result =
      typeof firstValue === "number" && typeof secondValue === "number"
        ? firstValue - secondValue
        : String(firstValue).localeCompare(String(secondValue))
    if (result !== 0) return direction === "asc" ? result : -result
    return first.id.localeCompare(second.id)
  })
}

export function groupMemories(memories: PreviewMemory[], group: MemoryGroupKey): MemoryGroup[] {
  if (group === "none") return [{ key: "all", label: "", rows: memories }]

  if (group === "agent") {
    const agents = [...new Set(memories.map((memory) => memory.agent))].sort((first, second) => first.localeCompare(second))
    return agents.map((agent) => ({
      key: `agent-${agent}`,
      label: agent,
      rows: memories.filter((memory) => memory.agent === agent),
    }))
  }

  if (group === "category") {
    return MEMORY_CATEGORIES.map((category) => ({
      key: `category-${category}`,
      label: MEMORY_CATEGORY_LABELS[category],
      rows: memories.filter((memory) => memory.category === category),
    })).filter((group) => group.rows.length > 0)
  }

  if (group === "lifecycle") {
    return MEMORY_STATUSES.map((status) => ({
      key: `lifecycle-${status}`,
      label: MEMORY_STATUS_LABELS[status],
      rows: memories.filter((memory) => memory.status === status),
    })).filter((group) => group.rows.length > 0)
  }

  return MEMORY_VISIBILITIES.map((visibility) => ({
    key: `scope-${visibility}`,
    label: MEMORY_VISIBILITY_LABELS[visibility],
    rows: memories.filter((memory) => memory.visibility === visibility),
  })).filter((group) => group.rows.length > 0)
}

export function hasActiveMemoryFilters(state: MemoryListState): boolean {
  const filters = state.filters
  return Boolean(
    filters.categories.length ||
      filters.statuses.length ||
      filters.visibilities.length ||
      filters.sources.length ||
      filters.agent ||
      filters.confidence ||
      filters.safety.length ||
      filters.validity ||
      filters.tags.length ||
      filters.retrieval,
  )
}

export function activeMemoryFilterCount(state: MemoryListState): number {
  const filters = state.filters
  return (
    filters.categories.length +
    filters.statuses.length +
    filters.visibilities.length +
    filters.sources.length +
    (filters.agent ? 1 : 0) +
    (filters.confidence ? 1 : 0) +
    filters.safety.length +
    (filters.validity ? 1 : 0) +
    filters.tags.length +
    (filters.retrieval ? 1 : 0)
  )
}

export function memoryViewIsModified(state: MemoryListState): boolean {
  return Boolean(state.search.trim()) || hasActiveMemoryFilters(state)
}

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "High · 0.90+",
  medium: "Medium · 0.75–0.89",
  low: "Low · below 0.75",
}

const VALIDITY_LABELS: Record<string, string> = {
  open: "Open",
  expiring: "Expiring · 30 days",
  expired: "Expired",
}

const SAFETY_LABELS: Record<MemorySafetyFlag, string> = {
  pii: "PII detected",
  injection: "Injection risk",
  conflict: "Open conflict",
}

const RETRIEVAL_LABELS: Record<string, string> = {
  never: "Never",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  frequent: "50+ retrievals",
}

export function activeMemoryFilterChips(state: MemoryListState): MemoryFilterChip[] {
  const filters = state.filters
  const chips: MemoryFilterChip[] = []

  function nextWith(patch: Partial<MemoryFilterState>): MemoryFilterState {
    return { ...filters, ...patch }
  }

  filters.categories.forEach((category) => {
    chips.push({
      key: `category-${category}`,
      field: "Category",
      value: MEMORY_CATEGORY_LABELS[category],
      next: nextWith({ categories: filters.categories.filter((entry) => entry !== category) }),
    })
  })

  filters.statuses.forEach((status) => {
    chips.push({
      key: `status-${status}`,
      field: "Lifecycle",
      value: MEMORY_STATUS_LABELS[status],
      next: nextWith({ statuses: filters.statuses.filter((entry) => entry !== status) }),
    })
  })

  filters.visibilities.forEach((visibility) => {
    chips.push({
      key: `visibility-${visibility}`,
      field: "Scope",
      value: MEMORY_VISIBILITY_LABELS[visibility],
      next: nextWith({ visibilities: filters.visibilities.filter((entry) => entry !== visibility) }),
    })
  })

  filters.sources.forEach((source) => {
    chips.push({
      key: `source-${source}`,
      field: "Source",
      value: MEMORY_SOURCE_LABELS[source],
      next: nextWith({ sources: filters.sources.filter((entry) => entry !== source) }),
    })
  })

  if (filters.agent) {
    chips.push({
      key: "agent",
      field: "Agent",
      value: filters.agent,
      next: nextWith({ agent: "" }),
    })
  }

  if (filters.confidence) {
    chips.push({
      key: "confidence",
      field: "Confidence",
      value: CONFIDENCE_LABELS[filters.confidence] ?? filters.confidence,
      next: nextWith({ confidence: "" }),
    })
  }

  filters.safety.forEach((flag) => {
    chips.push({
      key: `safety-${flag}`,
      field: "Flag",
      value: SAFETY_LABELS[flag],
      next: nextWith({ safety: filters.safety.filter((entry) => entry !== flag) }),
    })
  })

  if (filters.validity) {
    chips.push({
      key: "validity",
      field: "Validity",
      value: VALIDITY_LABELS[filters.validity] ?? filters.validity,
      next: nextWith({ validity: "" }),
    })
  }

  filters.tags.forEach((tag) => {
    chips.push({
      key: `tag-${tag}`,
      field: "Tag",
      value: tag,
      next: nextWith({ tags: filters.tags.filter((entry) => entry !== tag) }),
    })
  })

  if (filters.retrieval) {
    chips.push({
      key: "retrieval",
      field: "Retrieved",
      value: RETRIEVAL_LABELS[filters.retrieval] ?? filters.retrieval,
      next: nextWith({ retrieval: "" }),
    })
  }

  return chips
}

export function memoryUpdatedLabel(memory: PreviewMemory): string {
  return memory.updatedLabel
}

export function memoryRetrievedLabel(memory: PreviewMemory): string {
  return memoryRelativeTime(memory.lastRetrievedAt)
}

export function memoryAgentName(memory: PreviewMemory): string {
  return memory.agent
}

export function memoryScopeLabel(memory: PreviewMemory): string {
  return MEMORY_VISIBILITY_LABELS[memory.visibility]
}
