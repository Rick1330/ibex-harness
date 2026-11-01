import type {
  PublicOperatorContext,
  PublicOperatorOverview,
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
