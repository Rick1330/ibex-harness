"use client"

import { VIZ } from "@/lib/explore/viz-colors"
import { cn } from "@/lib/utils"

type LatencyParts = {
  auth_ms: number
  context_ms: number
  provider_ms: number
  stream_ms: number
  total_ms: number
}

const SEGMENTS = [
  { key: "auth", msKey: "auth_ms" as const, tone: "auth" as const },
  { key: "context", msKey: "context_ms" as const, tone: "context" as const },
  { key: "provider", msKey: "provider_ms" as const, tone: "provider" as const },
  { key: "stream", msKey: "stream_ms" as const, tone: "stream" as const },
]

export function LatencyMiniBar({
  auth_ms,
  context_ms,
  provider_ms,
  stream_ms,
  total_ms,
  className,
}: LatencyParts & { className?: string }) {
  const values = { auth_ms, context_ms, provider_ms, stream_ms }
  const total = Math.max(
    total_ms,
    auth_ms + context_ms + provider_ms + stream_ms,
    1,
  )

  return (
    <div className={cn("flex min-w-[7rem] flex-col gap-1", className)}>
      <div
        className="flex h-2 w-full overflow-hidden rounded-sm border border-border/50 bg-muted/60"
        role="img"
        aria-label={`Latency ${total_ms}ms: auth ${auth_ms}, context ${context_ms}, provider ${provider_ms}, stream ${stream_ms}`}
        title={`auth ${auth_ms} · context ${context_ms} · provider ${provider_ms} · stream ${stream_ms}`}
      >
        {SEGMENTS.map((s) => {
          const ms = values[s.msKey]
          if (ms <= 0) return null
          return (
            <div
              key={s.key}
              className={cn(
                "h-full border-r border-background/30 last:border-r-0",
                VIZ[s.tone].fill,
              )}
              style={{ width: `${(ms / total) * 100}%` }}
            />
          )
        })}
      </div>
      <span className="font-mono text-[13px] text-muted-foreground tabular-nums">
        {total_ms.toLocaleString()}ms
      </span>
    </div>
  )
}
