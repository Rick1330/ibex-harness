"use client"

import * as React from "react"

import { FRESHNESS_TONE } from "@/lib/shell-health"

type StreamState = "connecting" | "connected" | "reconnecting" | "unavailable"

const DOT_BY_STATE: Record<StreamState, string> = {
  connected: "bg-emerald-500",
  connecting: FRESHNESS_TONE.reconnecting.dot,
  reconnecting: FRESHNESS_TONE.reconnecting.dot,
  unavailable: FRESHNESS_TONE.stale.dot,
}

const LABEL_BY_STATE: Record<StreamState, string> = {
  connected: "SSE connected",
  connecting: "SSE connecting",
  reconnecting: "SSE reconnecting",
  unavailable: "SSE unavailable",
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
      <span className={`size-1.5 rounded-full ${DOT_BY_STATE[state]}`} aria-hidden />
      <span className="font-mono">operator events</span>
      <span>{LABEL_BY_STATE[state]}</span>
    </output>
  )
}
