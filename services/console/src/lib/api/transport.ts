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

function apiOrigin(): URL {
  const origin = process.env.IBEX_OPERATOR_API_ORIGIN
  if (!origin) throw new OperatorApiError(503, "API_ORIGIN_UNAVAILABLE", "Operator API origin is unavailable")
  try {
    const parsed = new URL(origin)
    if (!(["http:", "https:"].includes(parsed.protocol)) || parsed.username || parsed.password) {
      throw new Error("unsafe origin")
    }
    return parsed
  } catch {
    throw new OperatorApiError(503, "API_ORIGIN_INVALID", "Operator API origin is invalid")
  }
}

function apiUrl(path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new OperatorApiError(400, "API_PATH_INVALID", "Operator API path must be relative")
  }
  const origin = apiOrigin()
  const target = new URL(path, origin)
  if (target.origin !== origin.origin) {
    throw new OperatorApiError(400, "API_PATH_INVALID", "Operator API path changed origin")
  }
  return target.toString()
}

export async function fetchOperatorJson<T>(
  path: string,
  parse: (value: unknown) => T,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  const response = await fetch(apiUrl(path), {
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
