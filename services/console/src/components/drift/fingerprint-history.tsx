"use client"

import Link from "next/link"
import { panelClass } from "@/components/sessions/dashboard-shell"

import {
  ChartLegendSwatch,
  MetricTrend,
  MetricTrendGrid,
} from "@/components/charts/metric-trend"
import { ClusterStack, DualViolin } from "@/components/drift/evidence-table"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { FingerprintRow } from "@/lib/drift/types"
import { cn } from "@/lib/utils"

export function FingerprintHistory({
  fingerprints,
  alertWindowLabel,
}: {
  fingerprints: FingerprintRow[]
  /** Label of the detection window on the trend (e.g. "02-11"). */
  alertWindowLabel?: string
}) {
  const baseline = fingerprints.find((f) => f.is_baseline)
  const windows = fingerprints.filter((f) => !f.is_baseline)
  const latest = windows[windows.length - 1]
  const changePoint = windows.find((f) => f.adwin_change_point)

  const series = windows.map((f) => ({
    t: f.computed_at.slice(5, 10),
    avg_prompt_tokens: f.avg_prompt_tokens,
    tool_call_rate: f.tool_call_rate,
    error_rate: +(f.error_rate * 100).toFixed(2),
    avg_response_time_ms: f.avg_response_time_ms,
    directive_version: f.directive_version,
    adwin: f.adwin_change_point,
  }))

  return (
    <Card className={panelClass}>
      <CardHeader className="border-b border-border/60 px-4 py-3">
        <CardTitle className="text-[13px] font-medium">
          Fingerprint history
        </CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Baseline anchored · scalar trends with reference line · t-digest /
          multi-centroid shown as shape (not mean±std)
        </p>
      </CardHeader>
      <CardContent className="space-y-5 px-4 py-3">
        {/* Timeline with baseline pinned */}
        <div className="space-y-2">
          <div className="text-[11px] font-medium tracking-wide text-muted-foreground">
            Windows
          </div>
          <div className="relative flex flex-wrap items-center gap-2">
            {baseline ? (
              <TimelineChip
                pinned
                label="BASELINE"
                sub={baseline.computed_at.slice(0, 10)}
                directive={baseline.directive_version}
              />
            ) : null}
            <span className="text-muted-foreground/50" aria-hidden>
              →
            </span>
            {windows.map((f) => (
              <TimelineChip
                key={f.fingerprint_id}
                label={f.computed_at.slice(5, 10)}
                sub={f.adwin_change_point ? "ADWIN" : undefined}
                highlight={f.adwin_change_point}
                alert={
                  alertWindowLabel != null &&
                  f.computed_at.slice(5, 10) === alertWindowLabel
                }
                directive={f.directive_version}
              />
            ))}
          </div>
        </div>

        {/* Scalar trends — shared MetricTrend language */}
        <MetricTrendGrid>
          <MetricTrend
            title="avg_prompt_tokens"
            dataKey="avg_prompt_tokens"
            data={series}
            baseline={baseline?.avg_prompt_tokens}
            highlightX={alertWindowLabel}
            marks={
              changePoint
                ? [
                    {
                      x: changePoint.computed_at.slice(5, 10),
                      y: changePoint.avg_prompt_tokens,
                      tone: "destructive",
                    },
                  ]
                : undefined
            }
          />
          <MetricTrend
            title="tool_call_rate"
            dataKey="tool_call_rate"
            data={series}
            baseline={baseline?.tool_call_rate}
            highlightX={alertWindowLabel}
            marks={
              changePoint
                ? [
                    {
                      x: changePoint.computed_at.slice(5, 10),
                      y: changePoint.tool_call_rate,
                      tone: "destructive",
                    },
                  ]
                : undefined
            }
          />
          <MetricTrend
            title="error_rate (%)"
            dataKey="error_rate"
            data={series}
            baseline={
              baseline ? +(baseline.error_rate * 100).toFixed(2) : undefined
            }
            highlightX={alertWindowLabel}
            marks={
              changePoint
                ? [
                    {
                      x: changePoint.computed_at.slice(5, 10),
                      y: +(changePoint.error_rate * 100).toFixed(2),
                      tone: "destructive",
                    },
                  ]
                : undefined
            }
          />
          <MetricTrend
            title="avg_response_time_ms"
            dataKey="avg_response_time_ms"
            data={series}
            baseline={baseline?.avg_response_time_ms}
            highlightX={alertWindowLabel}
            marks={
              changePoint
                ? [
                    {
                      x: changePoint.computed_at.slice(5, 10),
                      y: changePoint.avg_response_time_ms,
                      tone: "destructive",
                    },
                  ]
                : undefined
            }
          />
        </MetricTrendGrid>

        {/* Distribution shapes — the redesign's visual contract */}
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-md border border-border/60 px-3 py-3">
            <div className="mb-1 text-[11px] font-medium text-muted-foreground">
              token_quantile_sketch (t-digest)
            </div>
            <p className="mb-3 text-[11px] text-muted-foreground">
              Right-skewed — violin shows p10–p90. A mean line would hide the
              tail growth that KS flagged.
            </p>
            {baseline && latest ? (
              <DualViolin
                baseline={baseline.token_sketch}
                current={latest.token_sketch}
                className="w-full max-w-[280px]"
              />
            ) : null}
            <div className="mt-3 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
              <span>
                baseline p50{" "}
                <span className="font-mono text-foreground">
                  {baseline?.token_sketch.p50}
                </span>
              </span>
              <span>
                current p50{" "}
                <span className="font-mono text-foreground">
                  {latest?.token_sketch.p50}
                </span>
              </span>
              <span>
                current p90{" "}
                <span className="font-mono text-foreground">
                  {latest?.token_sketch.p90}
                </span>
              </span>
            </div>
          </div>

          <div className="rounded-md border border-border/60 px-3 py-3">
            <div className="mb-1 text-[11px] font-medium text-muted-foreground">
              response_cluster_centroids
            </div>
            <p className="mb-3 text-[11px] text-muted-foreground">
              Multi-centroid membership — single-centroid smearing was a named
              Phase 4.5 bug; stacks show the shift.
            </p>
            {baseline ? (
              <div className="space-y-2">
                <div>
                  <div className="mb-1 text-[10px] text-muted-foreground">
                    baseline
                  </div>
                  <ClusterStack masses={baseline.cluster_masses} />
                  <ClusterLegend masses={baseline.cluster_masses} />
                </div>
                {latest ? (
                  <div>
                    <div className="mb-1 text-[10px] text-muted-foreground">
                      current window
                    </div>
                    <ClusterStack masses={latest.cluster_masses} />
                    <ClusterLegend masses={latest.cluster_masses} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground">
          <ChartLegendSwatch
            className="border-dashed border-muted-foreground"
            label="Baseline reference"
          />
          <ChartLegendSwatch className="bg-foreground" label="Window value" />
          <ChartLegendSwatch
            className="bg-destructive"
            label="ADWIN change point"
          />
          {alertWindowLabel ? (
            <ChartLegendSwatch
              className="bg-amber-500"
              label={`Alert window (${alertWindowLabel})`}
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function TimelineChip({
  label,
  sub,
  directive,
  pinned,
  highlight,
  alert,
}: {
  label: string
  sub?: string
  directive: number | null
  pinned?: boolean
  highlight?: boolean
  alert?: boolean
}) {
  return (
    <span
      className={cn(
        "inline-flex flex-col gap-0.5 rounded-md border px-2 py-1 text-[11px]",
        pinned &&
          "border-foreground/50 bg-foreground text-background shadow-sm",
        !pinned && highlight && "border-destructive/50 bg-destructive/5",
        !pinned && alert && "border-amber-500/60 bg-amber-500/10",
        !pinned &&
          !highlight &&
          !alert &&
          "border-border/70 text-muted-foreground",
      )}
    >
      <span className={cn("font-medium", pinned && "tracking-wide")}>
        {label}
        {sub && !pinned ? (
          <span className="ml-1 font-normal opacity-80">{sub}</span>
        ) : null}
      </span>
      <span className={cn("text-[10px]", pinned ? "opacity-80" : "")}>
        {sub && pinned ? <span>{sub} · </span> : null}
        {directive != null ? (
          <Link
            href={`/dashboard/directives?version=${directive}`}
            className={cn(
              "underline-offset-2 hover:underline",
              pinned ? "text-background" : "text-foreground",
            )}
          >
            dir v{directive}
          </Link>
        ) : (
          "—"
        )}
      </span>
    </span>
  )
}

function ClusterLegend({
  masses,
}: {
  masses: FingerprintRow["cluster_masses"]
}) {
  return (
    <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
      {masses.map((m) => (
        <span key={m.cluster}>
          {m.cluster}{" "}
          <span className="font-mono text-foreground">
            {(m.mass * 100).toFixed(0)}%
          </span>
        </span>
      ))}
    </div>
  )
}
