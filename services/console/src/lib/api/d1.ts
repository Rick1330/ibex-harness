import "server-only"

import {
  OperatorContextSchema,
  OperatorOverviewSchema,
  OperatorTraceDetailSchema,
  OperatorTraceListSchema,
  PlatformHealthSchema,
  type OperatorContext,
  type OperatorOverview,
  type OperatorTraceDetail,
  type OperatorTraceList,
  type PlatformHealth,
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

type SessionFetch<T> = {
  path: OperatorFetchPath
  parse: (value: unknown) => T
  cookieHeader?: string
  suffix?: string
  query?: URLSearchParams
}

async function fetchOperatorWithSession<T>(call: SessionFetch<T>): Promise<T> {
  return fetchOperatorJson(
    call.path,
    call.parse,
    { headers: { Cookie: sessionCookieHeader(call.cookieHeader) } },
    call.suffix ?? "",
    call.query,
  )
}

export async function fetchOperatorContext(cookieHeader?: string): Promise<OperatorContext> {
  return fetchOperatorWithSession({
    path: "context",
    parse: (value) => OperatorContextSchema.parse(value),
    cookieHeader,
  })
}

export async function fetchOperatorOverview(cookieHeader?: string): Promise<OperatorOverview> {
  return fetchOperatorWithSession({
    path: "overview",
    parse: (value) => OperatorOverviewSchema.parse(value),
    cookieHeader,
  })
}

export async function fetchOperatorPlatformHealth(cookieHeader?: string): Promise<PlatformHealth> {
  return fetchOperatorWithSession({
    path: "platformHealth",
    parse: (value) => PlatformHealthSchema.parse(value),
    cookieHeader,
  })
}

/** Unified D2 trace read: list (query), runs-by-traceId, or run detail. */
export async function fetchOperatorTraceResource(
  kind: "list",
  cookieHeader: string | undefined,
  query: URLSearchParams,
): Promise<OperatorTraceList>
export async function fetchOperatorTraceResource(
  kind: "runs",
  cookieHeader: string | undefined,
  traceId: string,
): Promise<OperatorTraceList>
export async function fetchOperatorTraceResource(
  kind: "detail",
  cookieHeader: string | undefined,
  runId: string,
): Promise<OperatorTraceDetail>
export async function fetchOperatorTraceResource(
  kind: "list" | "runs" | "detail",
  cookieHeader: string | undefined,
  arg: string | URLSearchParams,
): Promise<OperatorTraceList | OperatorTraceDetail> {
  if (kind === "list") {
    return fetchOperatorWithSession({
      path: "traces",
      parse: (value) => OperatorTraceListSchema.parse(value),
      cookieHeader,
      query: arg as URLSearchParams,
    })
  }
  if (kind === "runs") {
    return fetchOperatorWithSession({
      path: "traceDetail",
      parse: (value) => OperatorTraceListSchema.parse(value),
      cookieHeader,
      suffix: arg as string,
    })
  }
  return fetchOperatorWithSession({
    path: "runDetail",
    parse: (value) => OperatorTraceDetailSchema.parse(value),
    cookieHeader,
    suffix: arg as string,
  })
}
