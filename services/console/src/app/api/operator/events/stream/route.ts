import { cookies } from "next/headers"
import { NextResponse } from "next/server"

import { OperatorApiError, operatorApiUrl } from "@/lib/api/transport"

export const dynamic = "force-dynamic"

const NO_STORE = { "Cache-Control": "no-store" } as const

function jsonError(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status, headers: NO_STORE })
}

function rejectForeignOrigin(request: Request): NextResponse | null {
  const incomingOrigin = request.headers.get("origin")
  const requestOrigin = new URL(request.url).origin
  if (incomingOrigin && incomingOrigin !== requestOrigin) {
    return jsonError(403, "ORIGIN_REJECTED", "Request origin is not allowed")
  }
  return null
}

async function requireAccessCookie(): Promise<{ cookieName: string; accessCookie: string } | NextResponse> {
  const cookieName = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const accessCookie = (await cookies()).get(cookieName)?.value
  if (!accessCookie) {
    return jsonError(401, "SESSION_REQUIRED", "Operator session is required")
  }
  return { cookieName, accessCookie }
}

function resolveEventsTarget(): URL | NextResponse {
  try {
    const target = operatorApiUrl("events")
    if (target.protocol !== "https:") {
      return jsonError(503, "API_ORIGIN_INSECURE", "Operator API requires HTTPS")
    }
    return target
  } catch (error) {
    if (error instanceof OperatorApiError) {
      return jsonError(503, error.code, error.message)
    }
    return jsonError(503, "OPERATOR_STREAM_UNAVAILABLE", "Operator event stream is unavailable")
  }
}

function upstreamHeaders(cookieName: string, accessCookie: string, request: Request): Headers {
  const headers = new Headers({
    Accept: "text/event-stream",
    Cookie: `${cookieName}=${accessCookie}`,
  })
  const lastEventId = request.headers.get("last-event-id")
  if (lastEventId && /^\d{1,20}$/.test(lastEventId)) {
    headers.set("Last-Event-ID", lastEventId)
  }
  return headers
}

function proxyUpstream(upstream: Response): Response {
  const responseHeaders = new Headers({
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "X-Accel-Buffering": "no",
    "X-Content-Type-Options": "nosniff",
  })
  const contentType = upstream.headers.get("content-type")
  if (contentType) responseHeaders.set("Content-Type", contentType)
  const requestId = upstream.headers.get("x-request-id")
  if (requestId) responseHeaders.set("X-Request-ID", requestId)
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  })
}

export async function GET(request: Request) {
  const originRejection = rejectForeignOrigin(request)
  if (originRejection) return originRejection

  const session = await requireAccessCookie()
  if (session instanceof NextResponse) return session

  const target = resolveEventsTarget()
  if (target instanceof NextResponse) return target

  try {
    const upstream = await fetch(target, {
      method: "GET",
      headers: upstreamHeaders(session.cookieName, session.accessCookie, request),
      cache: "no-store",
      redirect: "error",
      signal: request.signal,
    })
    return proxyUpstream(upstream)
  } catch {
    return jsonError(503, "OPERATOR_STREAM_UNAVAILABLE", "Operator event stream is unavailable")
  }
}
