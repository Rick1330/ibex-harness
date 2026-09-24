"use client"

import {
  ChartLegendSwatch,
  MetricTrend,
  MetricTrendGrid,
} from "@/components/charts/metric-trend"
import type { TimeBucket } from "@/lib/analytics/types"
import { cn } from "@/lib/utils"

const compact = new Intl.NumberFormat("en-US", { notation: "compact" })

/**
 * Requests + tokens over time — fingerprint MetricTrend language
 * (bordered panels, dashed overlay, partial-bucket marks).
 */
export function RequestsTokensPlot({
  series,
  className,
  height = 180,
}: {
  series: TimeBucket[]
  className?: string
  height?: number
}) {
  const data = series.map((b) => ({
    t: b.hour.slice(11, 16) || b.hour.slice(5, 10),
    requests: b.requests,
    tokens_k: Math.round(b.tokens / 1000),
    partial: b.completeness === "partial",
  }))

  const partialMarks = data
    .filter((d) => d.partial)
    .map((d) => ({
      x: d.t,
      y: d.requests,
      tone: "destructive" as const,
    }))

  return (
    <div className={cn("space-y-3", className)}>
      <MetricTrendGrid>
        <MetricTrend
          title="requests"
          data={data}
          dataKey="requests"
          height={height}
          yFormatter={(v) => compact.format(v)}
          marks={partialMarks}
          config={{
            value: { label: "Requests", color: "var(--foreground)" },
          }}
        />
        <MetricTrend
          title="tokens (÷1k)"
          data={data}
          dataKey="tokens_k"
          height={height}
          yFormatter={(v) => compact.format(v)}
          marks={data
            .filter((d) => d.partial)
            .map((d) => ({
              x: d.t,
              y: d.tokens_k,
              tone: "destructive" as const,
            }))}
          config={{
            value: { label: "Tokens ÷1k", color: "var(--foreground)" },
          }}
        />
      </MetricTrendGrid>
      <div className="flex flex-wrap gap-4">
        <ChartLegendSwatch className="bg-foreground" label="Observed" />
        <ChartLegendSwatch
          className="bg-destructive"
          label="Partial ClickHouse bucket"
        />
      </div>
    </div>
  )
}
