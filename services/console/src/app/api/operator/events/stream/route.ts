import { cookies } from "next/headers"
import { NextResponse } from "next/server"

import { operatorApiUrl } from "@/lib/api/transport"

export const dynamic = "force-dynamic"

export async function GET(request: Request) {
  const incomingOrigin = request.headers.get("origin")
  const requestOrigin = new URL(request.url).origin
  if (incomingOrigin && incomingOrigin !== requestOrigin) {
    return NextResponse.json(
      { error: { code: "ORIGIN_REJECTED", message: "Request origin is not allowed" } },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    )
  }

  const cookieName = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const accessCookie = (await cookies()).get(cookieName)?.value
  if (!accessCookie) {
    return NextResponse.json(
      { error: { code: "SESSION_REQUIRED", message: "Operator session is required" } },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    )
  }

  const target = operatorApiUrl("events")
  if (target.protocol !== "https:") {
    return NextResponse.json(
      { error: { code: "API_ORIGIN_INSECURE", message: "Operator API requires HTTPS" } },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    )
  }

  const headers = new Headers({
    Accept: "text/event-stream",
    Cookie: `${cookieName}=${accessCookie}`,
  })
  const lastEventId = request.headers.get("last-event-id")
  if (lastEventId && /^\d{1,20}$/.test(lastEventId)) {
    headers.set("Last-Event-ID", lastEventId)
  }

  let upstream: Response
  try {
    upstream = await fetch(target, {
      method: "GET",
      headers,
      cache: "no-store",
      redirect: "error",
      signal: request.signal,
    })
  } catch {
    return NextResponse.json(
      { error: { code: "OPERATOR_STREAM_UNAVAILABLE", message: "Operator event stream is unavailable" } },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    )
  }

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
