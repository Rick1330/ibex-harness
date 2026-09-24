"use client"

import {
  ChartLegendSwatch,
  MetricTrend,
  MetricTrendGrid,
} from "@/components/charts/metric-trend"
import type { LatencyPercentiles } from "@/lib/analytics/types"
import { cn } from "@/lib/utils"

const STAGE_LABEL: Record<string, string> = {
  proxy_overhead: "proxy_overhead",
  context_assembly: "context_assembly",
  auth_validation: "auth_validation",
  rate_limit_check: "rate_limit_check",
  provider_latency: "provider_latency",
}

/**
 * Percentile trends per latency stage — fingerprint MetricTrend panels
 * with p95 target as dashed reference (not grouped bar soup).
 */
export function LatencyPercentileBars({
  stages,
  className,
}: {
  stages: LatencyPercentiles[]
  className?: string
}) {
  // Provider dwarfs gateway stages — split grids so auth/proxy stay readable.
  const light = stages.filter((s) => s.stage !== "provider_latency")
  const heavy = stages.filter((s) => s.stage === "provider_latency")

  return (
    <div className={cn("space-y-4", className)}>
      {light.length ? (
        <div className="space-y-2">
          <div className="text-[11px] font-medium text-muted-foreground">
            Gateway stages (ms)
          </div>
          <MetricTrendGrid>
            {light.map((s) => (
              <StageTrend key={s.stage} stage={s} />
            ))}
          </MetricTrendGrid>
        </div>
      ) : null}
      {heavy.length ? (
        <div className="space-y-2">
          <div className="text-[11px] font-medium text-muted-foreground">
            Provider stage (ms)
          </div>
          <MetricTrendGrid className="md:grid-cols-1">
            {heavy.map((s) => (
              <StageTrend key={s.stage} stage={s} height={160} />
            ))}
          </MetricTrendGrid>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-4">
        <ChartLegendSwatch
          className="border-dashed border-muted-foreground"
          label="p95 target"
        />
        <ChartLegendSwatch className="bg-foreground" label="p50 → p95 → p99" />
        <ChartLegendSwatch className="bg-amber-500" label="p99 mark" />
      </div>
    </div>
  )
}

function StageTrend({
  stage,
  height = 120,
}: {
  stage: LatencyPercentiles
  height?: number
}) {
  const label = STAGE_LABEL[stage.stage] ?? stage.stage
  return (
    <MetricTrend
      title={label}
      data={[
        { t: "p50", value: stage.p50 },
        { t: "p95", value: stage.p95 },
        { t: "p99", value: stage.p99 },
      ]}
      dataKey="value"
      referenceY={stage.target_p95_ms ?? undefined}
      referenceYLabel={stage.target_p95_ms != null ? "target" : undefined}
      height={height}
      yFormatter={(v) => `${v}`}
      marks={[{ x: "p99", y: stage.p99, tone: "amber" }]}
    />
  )
}
