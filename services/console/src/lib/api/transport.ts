import "server-only"

import { ApiErrorSchema } from "./contracts"

export class OperatorApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = "OperatorApiError"
    this.status = status
    this.code = code
  }
}

const OPERATOR_API_PATHS = {
  session: "/operator/session",
  operatorHealth: "/operator/health",
  platformHealth: "/platform/health",
} as const
type OperatorApiPath = keyof typeof OPERATOR_API_PATHS

function unavailableOrigin(): never {
  throw new OperatorApiError(503, "API_ORIGIN_UNAVAILABLE", "Operator API origin is unavailable")
}

function invalidOrigin(): never {
  throw new OperatorApiError(503, "API_ORIGIN_INVALID", "Operator API origin is invalid")
}

function assertHttpProtocol(parsed: URL): void {
  if (parsed.protocol === "http:") return
  if (parsed.protocol === "https:") return
  throw new Error("unsafe protocol")
}

function assertNoUserInfo(parsed: URL): void {
  if (parsed.username) throw new Error("unsafe username")
  if (parsed.password) throw new Error("unsafe password")
}

function apiOrigin(): URL {
  const origin = process.env.IBEX_OPERATOR_API_ORIGIN
  if (!origin) unavailableOrigin()
  try {
    const parsed = new URL(origin)
    assertHttpProtocol(parsed)
    assertNoUserInfo(parsed)
    return parsed
  } catch (error) {
    if (error instanceof OperatorApiError) throw error
    invalidOrigin()
  }
}

function pathnameFor(path: OperatorApiPath): string {
  switch (path) {
    case "session":
      return OPERATOR_API_PATHS.session
    case "operatorHealth":
      return OPERATOR_API_PATHS.operatorHealth
    case "platformHealth":
      return OPERATOR_API_PATHS.platformHealth
    default: {
      const _exhaustive: never = path
      throw new OperatorApiError(400, "API_PATH_INVALID", `Unknown operator API path: ${_exhaustive}`)
    }
  }
}

function apiUrl(path: OperatorApiPath): string {
  const origin = apiOrigin()
  const target = new URL(pathnameFor(path), origin)
  if (target.origin !== origin.origin) {
    throw new OperatorApiError(400, "API_PATH_INVALID", "Operator API path changed origin")
  }
  return target.toString()
}

export async function fetchOperatorJson<T>(
  path: OperatorApiPath,
  parse: (value: unknown) => T,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  // Origin is server env only; path is a fixed allowlist key (OperatorApiPath).
  const url = apiUrl(path)
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    // Server components do not have a browser cookie jar. Callers must forward
    // the request Cookie header explicitly after Next.js request validation.
    headers,
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(body)
    throw new OperatorApiError(
      response.status,
      parsed.success ? parsed.data.error.code : "API_REQUEST_FAILED",
      parsed.success ? parsed.data.error.message : "Operator API request failed",
    )
  }
  return parse(body)
}
