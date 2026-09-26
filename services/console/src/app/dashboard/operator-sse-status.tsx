"use client"

import * as React from "react"

import { FRESHNESS_TONE } from "@/lib/shell-health"

type StreamState = "connecting" | "connected" | "reconnecting" | "unavailable"

export function OperatorSseStatus() {
  const [state, setState] = React.useState<StreamState>("connecting")
  React.useEffect(() => {
    let closed = false
    let unavailableTimer: number | undefined
    const stream = new EventSource("/api/operator/events/stream")
    stream.onopen = () => {
      if (closed) return
      if (unavailableTimer) window.clearTimeout(unavailableTimer)
      setState("connected")
    }
    stream.onerror = () => {
      if (closed) return
      setState(stream.readyState === EventSource.CLOSED ? "unavailable" : "reconnecting")
      if (unavailableTimer) window.clearTimeout(unavailableTimer)
      unavailableTimer = window.setTimeout(() => {
        if (!closed && stream.readyState !== EventSource.OPEN) setState("unavailable")
      }, 30_000)
    }
    // Do not parse, render, store, or log event payloads. Native EventSource
    // manages reconnect and Last-Event-ID resume after transport loss.
    stream.addEventListener("operator.evidence", () => undefined)
    return () => {
      closed = true
      if (unavailableTimer) window.clearTimeout(unavailableTimer)
      stream.close()
    }
  }, [])

  const dot = state === "connected"
    ? "bg-emerald-500"
    : state === "unavailable"
      ? FRESHNESS_TONE.stale.dot
      : FRESHNESS_TONE.reconnecting.dot
  const label = state === "connected"
    ? "SSE connected"
    : state === "connecting"
      ? "SSE connecting"
      : state === "reconnecting"
        ? "SSE reconnecting"
        : "SSE unavailable"

  return (
    <span role="status" aria-live="polite" className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden />
      <span className="font-mono">operator events</span>
      <span>{label}</span>
    </span>
  )
}
