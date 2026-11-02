import { computed } from "vue"
import type {
  PublicOperatorAgent,
  PublicOperatorAgentPage,
  PublicOperatorContext,
  PublicOperatorDirectiveDetail,
  PublicOperatorDirectivePage,
  PublicOperatorEvidenceSummary,
  PublicOperatorMemory,
  PublicOperatorMemoryPage,
  PublicOperatorOverview,
  PublicOperatorSessionRecordDetail,
  PublicOperatorSessionRecordPage,
  PublicOperatorTraceDetail,
  PublicOperatorTraceList,
  PublicPlatformHealth,
} from "~~/shared/operator/public"

export function useOperatorContext() {
  return useAsyncData<PublicOperatorContext>("operator-context", () => {
    return useRequestFetch()("/api/operator/context")
  })
}

export function useOperatorOverview() {
  return useAsyncData<PublicOperatorOverview>("operator-overview", () => {
    return useRequestFetch()("/api/operator/overview")
  })
}

export function usePlatformHealth() {
  return useAsyncData<PublicPlatformHealth>("operator-platform-health", () => {
    return useRequestFetch()("/api/operator/platform/health")
  })
}

export function useTraceList(params: URLSearchParams, enabled = true) {
  const query = params.toString()
  return useAsyncData<PublicOperatorTraceList | null>(`operator-traces:${enabled ? query : "disabled"}`, () => {
    if (!enabled) return Promise.resolve(null)
    return useRequestFetch()(`/api/operator/traces${query ? `?${query}` : ""}`)
  })
}

export function useTraceRuns(traceId: string) {
  return useAsyncData<PublicOperatorTraceList>(`operator-trace-runs:${traceId}`, () => {
    return useRequestFetch()(`/api/operator/traces/${encodeURIComponent(traceId)}`)
  })
}

export function useTraceDetail(runId: string) {
  return useAsyncData<PublicOperatorTraceDetail>(`operator-trace-detail:${runId}`, () => {
    return useRequestFetch()(`/api/operator/traces/runs/${encodeURIComponent(runId)}`)
  })
}

export function useOperatorAgents(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/agents${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorAgentPage>(url, { key: url, watch: [url] })
}

export function useOperatorAgent(agentId: () => string) {
  const url = computed(() => `/api/operator/agents/${encodeURIComponent(agentId())}`)
  return useFetch<PublicOperatorAgent>(url, { key: url, watch: [url] })
}

export function useOperatorMemories(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/memories${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorMemoryPage>(url, { key: url, watch: [url] })
}

export function useOperatorMemory(memoryId: () => string) {
  const url = computed(() => `/api/operator/memories/${encodeURIComponent(memoryId())}`)
  return useFetch<PublicOperatorMemory>(url, { key: url, watch: [url] })
}

export function useOperatorDirectives(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/directives${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorDirectivePage>(url, { key: url, watch: [url] })
}

export function useOperatorDirective(directiveId: () => string, params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/directives/${encodeURIComponent(directiveId())}${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorDirectiveDetail>(url, { key: url, watch: [url] })
}

export function useOperatorEvidenceSummary(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/evidence/summary${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorEvidenceSummary>(url, { key: url, watch: [url] })
}

export function useOperatorSessions(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/sessions${query ? `?${query}` : ""}`
  })
  return useFetch<PublicOperatorSessionRecordPage>(url, { key: url, watch: [url] })
}

export function useOperatorSession(sessionId: () => string) {
  const url = computed(() => `/api/operator/sessions/${encodeURIComponent(sessionId())}`)
  return useFetch<PublicOperatorSessionRecordDetail>(url, { key: url, watch: [url] })
}
