import { getHeader, getRequestURL, setResponseHeader } from "h3"
import { operatorTarget, sessionCookie } from "~~/server/utils/operator/http"

function jsonError(statusCode: number, code: string, message: string): never {
  throw createError({
    statusCode,
    statusMessage: message,
    data: { error: { code, message } },
  })
}

export default defineEventHandler(async (event) => {
  setResponseHeader(event, "Cache-Control", "no-store")
  setResponseHeader(event, "Vary", "Cookie")

  const origin = getHeader(event, "origin")
  const requestOrigin = getRequestURL(event).origin
  if (origin && origin !== requestOrigin) {
    jsonError(403, "ORIGIN_REJECTED", "Request origin is not allowed")
  }

  const cookie = sessionCookie(event)
  if (!cookie.header) {
    jsonError(401, "SESSION_REQUIRED", "Operator session is required")
  }

  let target: URL
  try {
    target = operatorTarget(event, "events")
  } catch {
    jsonError(503, "OPERATOR_STREAM_UNAVAILABLE", "Operator event stream is unavailable")
  }
  if (target.protocol !== "https:") {
    jsonError(503, "API_ORIGIN_INSECURE", "Operator API requires HTTPS")
  }

  const headers = new Headers({
    Accept: "text/event-stream",
    Cookie: cookie.header,
  })
  const lastEventId = getHeader(event, "last-event-id")
  if (lastEventId && /^\d{1,20}$/.test(lastEventId)) {
    headers.set("Last-Event-ID", lastEventId)
  }

  const controller = new AbortController()
  event.node.req.once("close", () => controller.abort())

  try {
    const upstream = await fetch(new URL("/v1/operator/events/stream", target.origin), {
      method: "GET",
      headers,
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    })

    setResponseHeader(event, "Content-Type", "text/event-stream; charset=utf-8")
    setResponseHeader(event, "X-Accel-Buffering", "no")
    setResponseHeader(event, "X-Content-Type-Options", "nosniff")
    const requestId = upstream.headers.get("x-request-id")
    if (requestId) setResponseHeader(event, "X-Request-ID", requestId)

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "text/event-stream",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",
      },
    })
  } catch {
    if (controller.signal.aborted) return new Response(null, { status: 499 })
    jsonError(503, "OPERATOR_STREAM_UNAVAILABLE", "Operator event stream is unavailable")
  }
})
