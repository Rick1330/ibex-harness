"use client"

import * as React from "react"

type StreamState = "connecting" | "connected" | "reconnecting" | "unavailable"

function streamDotClass(state: StreamState): string {
  switch (state) {
    case "connected":
      return "bg-emerald-500"
    case "connecting":
    case "reconnecting":
      return "bg-amber-500"
    case "unavailable":
      return "bg-destructive"
  }
}

function streamLabel(state: StreamState): string {
  switch (state) {
    case "connected":
      return "SSE connected"
    case "connecting":
      return "SSE connecting"
    case "reconnecting":
      return "SSE reconnecting"
    case "unavailable":
      return "SSE unavailable"
  }
}

function attachOperatorEventSource(onState: (state: StreamState) => void): () => void {
  let closed = false
  let unavailableTimer: number | undefined
  const stream = new EventSource("/api/operator/events/stream")
  stream.onopen = () => {
    if (closed) return
    if (unavailableTimer) window.clearTimeout(unavailableTimer)
    onState("connected")
  }
  stream.onerror = () => {
    if (closed) return
    onState(stream.readyState === EventSource.CLOSED ? "unavailable" : "reconnecting")
    if (unavailableTimer) window.clearTimeout(unavailableTimer)
    unavailableTimer = window.setTimeout(() => {
      if (!closed && stream.readyState !== EventSource.OPEN) onState("unavailable")
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
}

export function OperatorSseStatus() {
  const [state, setState] = React.useState<StreamState>("connecting")
  React.useEffect(() => attachOperatorEventSource(setState), [])

  return (
    <output aria-live="polite" className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={`size-1.5 rounded-full ${streamDotClass(state)}`} aria-hidden />
      <span className="font-mono">operator events</span>
      <span>{streamLabel(state)}</span>
    </output>
  )
}
