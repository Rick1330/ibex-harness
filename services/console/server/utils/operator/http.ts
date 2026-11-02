import type { H3Event } from "h3"
import { getCookie, setResponseHeader } from "h3"
import { ApiErrorSchema } from "~~/shared/operator/contracts"

const OPERATOR_PATHS = {
  context: "/v1/operator/context",
  overview: "/v1/operator/overview",
  platformHealth: "/v1/operator/platform/health",
  events: "/v1/operator/events/stream",
  traces: "/v1/operator/traces",
  traceDetail: "/v1/operator/traces/",
  runDetail: "/v1/operator/traces/runs/",
  agents: "/v1/operator/agents",
  agentDetail: "/v1/operator/agents/",
  memories: "/v1/operator/memories",
  memoryDetail: "/v1/operator/memories/",
} as const

const TRACE_ID_RE = /^[A-Za-z0-9._~-]{1,256}$/
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SUFFIX_PATHS = new Set<OperatorPath>(["traceDetail", "runDetail", "agentDetail", "memoryDetail"])

export type OperatorPath = keyof typeof OPERATOR_PATHS

export class OperatorUpstreamError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null = null) {
    super(message)
    this.name = "OperatorUpstreamError"
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

function configuredOrigin(event: H3Event): URL {
  const config = useRuntimeConfig(event)
  const raw =
    process.env.IBEX_OPERATOR_API_ORIGIN?.trim() ||
    String(config.operatorApiOrigin ?? "").trim()
  if (!raw) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_UNAVAILABLE",
      "Operator API origin is unavailable",
    )
  }

  let origin: URL
  try {
    origin = new URL(raw)
  } catch {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }

  const hasUserinfo = Boolean(origin.username || origin.password)
  const hasPath = origin.pathname !== "/" || Boolean(origin.search) || Boolean(origin.hash)
  const protocolAllowed = origin.protocol === "http:" || origin.protocol === "https:"
  if (!protocolAllowed || hasUserinfo || hasPath) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }
  return origin
}

export function operatorTarget(
  event: H3Event,
  path: OperatorPath,
  suffix = "",
  query?: URLSearchParams,
): URL {
  const origin = configuredOrigin(event)
  if (suffix && !SUFFIX_PATHS.has(path)) {
    throw new OperatorUpstreamError(404, "NOT_FOUND", "Not found")
  }
  if (suffix) {
    const pattern = path === "agentDetail" || path === "memoryDetail" ? UUID_RE : TRACE_ID_RE
    if (!pattern.test(suffix)) {
      throw new OperatorUpstreamError(404, "NOT_FOUND", "Not found")
    }
  }

  const target = new URL(`${OPERATOR_PATHS[path]}${encodeURIComponent(suffix)}`, origin)
  if (query) target.search = query.toString()
  if (target.origin !== origin.origin) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }
  return target
}

export function sessionCookie(event: H3Event): { name: string; header: string } {
  const config = useRuntimeConfig(event)
  const name =
    process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME?.trim() ||
    String(config.operatorSessionCookieName ?? "ibex_session")
  const value = getCookie(event, name)
  return { name, header: value ? `${name}=${value}` : "" }
}

function hasCookie(header: string): boolean {
  return header.trim().length > 0
}

export async function fetchOperatorJson<T>(
  event: H3Event,
  path: OperatorPath,
  parse: (value: unknown) => T,
  options: {
    suffix?: string
    query?: URLSearchParams
    signal?: AbortSignal
  } = {},
): Promise<T> {
  const target = operatorTarget(event, path, options.suffix, options.query)
  const cookie = sessionCookie(event)
  if (hasCookie(cookie.header) && target.protocol !== "https:") {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator session cookies require an HTTPS API origin",
    )
  }

  const headers = new Headers({ Accept: "application/json" })
  if (cookie.header) headers.set("Cookie", cookie.header)

  let response: Response
  try {
    response = await fetch(target, {
      cache: "no-store",
      redirect: "error",
      signal: options.signal ?? AbortSignal.timeout(5_000),
      headers,
    })
  } catch {
    throw new OperatorUpstreamError(
      503,
      "OPERATOR_API_UNREACHABLE",
      "Operator API is unavailable",
    )
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(body)
    throw new OperatorUpstreamError(
      response.status,
      parsed.success ? parsed.data.error.code : "API_REQUEST_FAILED",
      parsed.success ? parsed.data.error.message : "Operator API request failed",
      parsed.success ? (parsed.data.error.request_id ?? null) : null,
    )
  }

  try {
    return parse(body)
  } catch {
    throw new OperatorUpstreamError(
      502,
      "INVALID_UPSTREAM_PAYLOAD",
      "Operator API returned an invalid payload",
    )
  }
}

export function noStore(event: H3Event): void {
  setResponseHeader(event, "Cache-Control", "private, no-store")
  setResponseHeader(event, "Vary", "Cookie")
}

export function toHttpError(error: unknown): never {
  if (error instanceof OperatorUpstreamError) {
    const statusCode = error.status >= 400 && error.status <= 599 ? error.status : 502
    throw createError({
      statusCode,
      statusMessage: error.message,
      data: {
        error: {
          code: error.code,
          message: error.message,
          ...(error.requestId ? { request_id: error.requestId } : {}),
        },
      },
    })
  }
  throw createError({
    statusCode: 503,
    statusMessage: "Operator API is unavailable",
    data: {
      error: {
        code: "OPERATOR_API_UNAVAILABLE",
        message: "Operator API is unavailable",
      },
    },
  })
}
