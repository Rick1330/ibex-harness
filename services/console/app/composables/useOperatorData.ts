import { computed } from "vue"
import type {
  PublicOperatorAgent,
  PublicOperatorAgentPage,
  PublicOperatorContext,
  PublicOperatorDirectiveDetail,
  PublicOperatorDirectivePage,
  PublicOperatorEvidenceDeletions,
  PublicOperatorEvidenceSummary,
  PublicOperatorMemoryDetail,
  PublicOperatorMemoryPage,
  PublicOperatorOverview,
  PublicOperatorSessionRecordDetail,
  PublicOperatorSessionRecordPage,
  PublicOperatorTraceDetail,
  PublicOperatorTraceList,
  PublicPlatformHealth,
} from "~~/shared/operator/public"

type OperatorResponseError = Error & {
  statusCode: number
  status: number
  statusText: string
  data: unknown
}

/** Parse a BFF body the way ofetch's `destr` does: JSON when possible, text otherwise. */
function parseOperatorBody(text: string): unknown {
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/**
 * Apply an operator BFF response to the outer SSR response and return its body.
 *
 * `Set-Cookie` is relayed verbatim: cookie flags are the API's decision and are
 * never rewritten here. A 4xx/5xx throws an `Error` carrying `statusCode` and
 * the parsed body in `data`, matching the `FetchError` ofetch throws on the
 * client so `useAsyncData` reports the same failure on both paths.
 */
export async function applyOperatorResponse<T>(
  response: Response,
  appendCookie: (cookie: string) => void,
): Promise<T> {
  for (const cookie of response.headers.getSetCookie()) {
    appendCookie(cookie)
  }
  const data = parseOperatorBody(await response.text())
  if (response.status >= 400) {
    const error = new Error(
      `[GET] ${JSON.stringify(response.url)}: ${response.status} ${response.statusText}`,
    ) as OperatorResponseError
    error.statusCode = response.status
    error.status = response.status
    error.statusText = response.statusText
    error.data = data
    throw error
  }
  return data as T
}

/**
 * Read an operator BFF route, relaying its cookies to the outer SSR response.
 *
 * On the server `useRequestFetch()` resolves to `event.$fetch`, which Nitro wires
 * through h3's `fetchWithEvent`: it forwards request headers only and resolves to
 * the parsed body, so a `Set-Cookie` the inner route emitted is discarded and the
 * browser keeps the stale access cookie after a server-side session refresh.
 * `event.fetch` returns the raw `Response`, whose cookies are appended to the page
 * response. On the client there is no outer SSR response; the browser applies the
 * header itself.
 */
function requestOperator<T>(path: string): Promise<T> {
  const event = useRequestEvent()
  if (!event) {
    const request = useRequestFetch()
    return request(path) as Promise<T>
  }
  return event
    .fetch(path)
    .then((response) =>
      applyOperatorResponse<T>(response, (cookie) =>
        event.node.res.appendHeader("set-cookie", cookie),
      ),
    )
}

export function useOperatorContext() {
  return useAsyncData<PublicOperatorContext>("operator-context", () => {
    return requestOperator<PublicOperatorContext>("/api/operator/context")
  })
}

export function useOperatorOverview() {
  return useAsyncData<PublicOperatorOverview>("operator-overview", () => {
    return requestOperator<PublicOperatorOverview>("/api/operator/overview")
  })
}

export function usePlatformHealth() {
  return useAsyncData<PublicPlatformHealth>("operator-platform-health", () => {
    return requestOperator<PublicPlatformHealth>("/api/operator/platform/health")
  })
}

export function useTraceList(params: URLSearchParams, enabled = true) {
  const query = params.toString()
  return useAsyncData<PublicOperatorTraceList | null>(`operator-traces:${enabled ? query : "disabled"}`, () => {
    if (!enabled) return Promise.resolve(null)
    return requestOperator<PublicOperatorTraceList>(`/api/operator/traces${query ? `?${query}` : ""}`)
  })
}

export function useTraceRuns(traceId: string) {
  return useAsyncData<PublicOperatorTraceList>(`operator-trace-runs:${traceId}`, () => {
    return requestOperator<PublicOperatorTraceList>(`/api/operator/traces/${encodeURIComponent(traceId)}`)
  })
}

export function useTraceDetail(runId: string) {
  return useAsyncData<PublicOperatorTraceDetail>(`operator-trace-detail:${runId}`, () => {
    return requestOperator<PublicOperatorTraceDetail>(`/api/operator/traces/runs/${encodeURIComponent(runId)}`)
  })
}

export function useOperatorAgents(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/agents${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorAgentPage>(url, () => requestOperator<PublicOperatorAgentPage>(url.value), {
    watch: [url],
  })
}

export function useOperatorAgent(agentId: () => string) {
  const url = computed(() => `/api/operator/agents/${encodeURIComponent(agentId())}`)
  return useAsyncData<PublicOperatorAgent>(url, () => requestOperator<PublicOperatorAgent>(url.value), {
    watch: [url],
  })
}

export function useOperatorMemories(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/memories${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorMemoryPage>(url, () => requestOperator<PublicOperatorMemoryPage>(url.value), {
    watch: [url],
  })
}

export function useOperatorMemory(memoryId: () => string) {
  const url = computed(() => `/api/operator/memories/${encodeURIComponent(memoryId())}`)
  return useAsyncData<PublicOperatorMemoryDetail>(url, () => requestOperator<PublicOperatorMemoryDetail>(url.value), {
    watch: [url],
  })
}

export function useOperatorDirectives(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/directives${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorDirectivePage>(url, () => requestOperator<PublicOperatorDirectivePage>(url.value), {
    watch: [url],
  })
}

export function useOperatorDirective(directiveId: () => string, params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/directives/${encodeURIComponent(directiveId())}${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorDirectiveDetail>(
    url,
    () => requestOperator<PublicOperatorDirectiveDetail>(url.value),
    { watch: [url] },
  )
}

export function useOperatorEvidenceDeletions(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/evidence/deletions${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorEvidenceDeletions>(
    url,
    () => requestOperator<PublicOperatorEvidenceDeletions>(url.value),
    { watch: [url] },
  )
}

export function useOperatorEvidenceSummary(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/evidence/summary${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorEvidenceSummary>(url, () => requestOperator<PublicOperatorEvidenceSummary>(url.value), {
    watch: [url],
  })
}

export function useOperatorSessions(params: () => URLSearchParams) {
  const url = computed(() => {
    const query = params().toString()
    return `/api/operator/sessions${query ? `?${query}` : ""}`
  })
  return useAsyncData<PublicOperatorSessionRecordPage>(
    url,
    () => requestOperator<PublicOperatorSessionRecordPage>(url.value),
    { watch: [url] },
  )
}

export function useOperatorSession(sessionId: () => string) {
  const url = computed(() => `/api/operator/sessions/${encodeURIComponent(sessionId())}`)
  return useAsyncData<PublicOperatorSessionRecordDetail>(
    url,
    () => requestOperator<PublicOperatorSessionRecordDetail>(url.value),
    { watch: [url] },
  )
}
