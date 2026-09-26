import "server-only"

import {
  OperatorContextSchema,
  OperatorOverviewSchema,
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

export async function fetchOperatorContext(cookieHeader?: string) {
  return fetchOperatorJson(
    "context",
    (value) => OperatorContextSchema.parse(value),
    { headers: { Cookie: sessionCookieHeader(cookieHeader) } },
  )
}

export async function fetchOperatorOverview(cookieHeader?: string) {
  return fetchOperatorJson(
    "overview",
    (value) => OperatorOverviewSchema.parse(value),
    { headers: { Cookie: sessionCookieHeader(cookieHeader) } },
  )
}

export async function fetchOperatorPlatformHealth(cookieHeader?: string) {
  return fetchOperatorJson(
    "platformHealth",
    (value) => PlatformHealthSchema.parse(value),
    { headers: { Cookie: sessionCookieHeader(cookieHeader) } },
  )
}
