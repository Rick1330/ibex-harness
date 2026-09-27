import "server-only"

import {
  OperatorContextSchema,
  OperatorOverviewSchema,
  OperatorTraceDetailSchema,
  OperatorTraceListSchema,
  PlatformHealthSchema,
} from "./contracts"
import { fetchOperatorJson } from "./transport"

/** D1 reads forward only the access-session cookie, never refresh or CSRF cookies. */
function sessionCookieHeader(cookieHeader: string | undefined): string {
  if (!cookieHeader) return ""
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const wanted = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`))
  return wanted ?? ""
}

type OperatorFetchPath = Parameters<typeof fetchOperatorJson>[0]

async function fetchOperatorWithSession<T>(
  path: OperatorFetchPath,
  parse: (value: unknown) => T,
  cookieHeader: string | undefined,
  suffix = "",
  query?: URLSearchParams,
): Promise<T> {
  return fetchOperatorJson(
    path,
    parse,
    { headers: { Cookie: sessionCookieHeader(cookieHeader) } },
    suffix,
    query,
  )
}

export async function fetchOperatorContext(cookieHeader?: string) {
  return fetchOperatorWithSession("context", (value) => OperatorContextSchema.parse(value), cookieHeader)
}

export async function fetchOperatorOverview(cookieHeader?: string) {
  return fetchOperatorWithSession("overview", (value) => OperatorOverviewSchema.parse(value), cookieHeader)
}

export async function fetchOperatorPlatformHealth(cookieHeader?: string) {
  return fetchOperatorWithSession("platformHealth", (value) => PlatformHealthSchema.parse(value), cookieHeader)
}

export async function fetchOperatorTraces(
  cookieHeader: string | undefined,
  query: URLSearchParams,
) {
  return fetchOperatorWithSession(
    "traces",
    (value) => OperatorTraceListSchema.parse(value),
    cookieHeader,
    "",
    query,
  )
}

export async function fetchOperatorTraceRuns(cookieHeader: string | undefined, traceId: string) {
  return fetchOperatorWithSession(
    "traceDetail",
    (value) => OperatorTraceListSchema.parse(value),
    cookieHeader,
    traceId,
  )
}

export async function fetchOperatorTraceDetail(cookieHeader: string | undefined, runId: string) {
  return fetchOperatorWithSession(
    "runDetail",
    (value) => OperatorTraceDetailSchema.parse(value),
    cookieHeader,
    runId,
  )
}
