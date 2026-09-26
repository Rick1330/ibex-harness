import "server-only"

import { ApiErrorSchema } from "./contracts"

export class OperatorApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null = null) {
    super(message)
    this.name = "OperatorApiError"
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

const OPERATOR_API_PATHS = {
  context: "/v1/operator/context",
  overview: "/v1/operator/overview",
  platformHealth: "/v1/operator/platform/health",
  events: "/v1/operator/events/stream",
} as const
type OperatorApiPath = keyof typeof OPERATOR_API_PATHS

function unavailableOrigin(): never {
  throw new OperatorApiError(503, "API_ORIGIN_UNAVAILABLE", "Operator API origin is unavailable")
}

function invalidOrigin(): never {
  throw new OperatorApiError(503, "API_ORIGIN_INVALID", "Operator API origin is invalid")
}

function assertHttpOriginProtocol(origin: URL): void {
  if (origin.protocol === "http:") return
  if (origin.protocol === "https:") return
  throw new Error("unsafe protocol")
}

function assertNoUserinfo(origin: URL): void {
  if (origin.username) throw new Error("userinfo not allowed")
  if (origin.password) throw new Error("userinfo not allowed")
}

function assertOriginHasNoPath(origin: URL): void {
  if (origin.pathname !== "/") throw new Error("API configuration must be an origin without a path")
  if (origin.search) throw new Error("API configuration must be an origin without a path")
  if (origin.hash) throw new Error("API configuration must be an origin without a path")
}

function assertSafeOperatorOrigin(origin: URL): void {
  assertHttpOriginProtocol(origin)
  assertNoUserinfo(origin)
  assertOriginHasNoPath(origin)
}

export function operatorApiUrl(path: OperatorApiPath): URL {
  const rawOrigin = process.env.IBEX_OPERATOR_API_ORIGIN
  if (!rawOrigin) unavailableOrigin()
  try {
    const origin = new URL(rawOrigin)
    assertSafeOperatorOrigin(origin)
    const target = new URL(OPERATOR_API_PATHS[path], origin)
    if (target.origin !== origin.origin) throw new Error("path changed origin")
    return target
  } catch (error) {
    if (error instanceof OperatorApiError) throw error
    invalidOrigin()
  }
}

function assertNoCleartextSessionCookie(target: URL, headers: Headers): void {
  if (headers.get("cookie")?.trim() && target.protocol !== "https:") {
    throw new OperatorApiError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator session cookies require an HTTPS API origin",
    )
  }
}

export async function fetchOperatorJson<T>(
  path: OperatorApiPath,
  parse: (value: unknown) => T,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  const target = operatorApiUrl(path)
  assertNoCleartextSessionCookie(target, headers)
  // Origin is IBEX_OPERATOR_API_ORIGIN (server env); path is OperatorApiPath allowlist.
  // nosemgrep
  const response = await fetch(target.toString(), {
    ...init,
    cache: "no-store",
    redirect: "error",
    signal: init.signal ?? AbortSignal.timeout(5000),
    headers,
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(body)
    throw new OperatorApiError(
      response.status,
      parsed.success ? parsed.data.error.code : "API_REQUEST_FAILED",
      parsed.success ? parsed.data.error.message : "Operator API request failed",
      parsed.success ? parsed.data.error.request_id ?? null : null,
    )
  }
  return parse(body)
}
