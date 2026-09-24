"use client"

import type { ReactNode } from "react"

import { StatusDot } from "@/components/list/status-dot"
import { FEATURE_LABEL, TEST_LABEL } from "@/lib/drift/labels"
import type {
  ClusterMass,
  FeatureEvidence,
  QuantileSketch,
  ToolMass,
} from "@/lib/drift/types"
import { cn } from "@/lib/utils"

/**
 * Per-feature evidence — stacked cards (not a cramped 7-col table).
 * Table cells use whitespace-nowrap by default which caused Baseline text
 * to spill into Distribution charts.
 */
export function EvidenceTable({ evidence }: { evidence: FeatureEvidence[] }) {
  return (
    <ul className="divide-y divide-border/60">
      {evidence.map((e) => (
        <li key={e.feature_class} className="px-4 py-4">
          <EvidenceCard e={e} />
        </li>
      ))}
    </ul>
  )
}

function EvidenceCard({ e }: { e: FeatureEvidence }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(200px,240px)]">
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[13px] font-medium">
              {FEATURE_LABEL[e.feature_class]}
            </div>
            <div className="font-mono text-[11px] text-muted-foreground">
              {e.feature_class}
            </div>
          </div>
          {e.flagged ? (
            <StatusDot tone="error" label="flagged" />
          ) : (
            <StatusDot tone="ok" label="within threshold" />
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Test" value={TEST_LABEL[e.test]} mono={false} />
          <Metric label="test_statistic" value={formatStat(e.test_statistic)} />
          <div className="min-w-0">
            <div className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              threshold_used
            </div>
            <div className="mt-0.5 font-mono text-[13px] tabular-nums">
              {formatStat(e.threshold_used)}
            </div>
            <ThresholdBar
              statistic={e.test_statistic}
              threshold={e.threshold_used}
              flagged={e.flagged}
            />
          </div>
          <Metric
            label="n / p"
            value={
              <>
                n<sub>b</sub> {e.n_baseline.toLocaleString()} · n<sub>c</sub>{" "}
                {e.n_current.toLocaleString()}
                <span className="mt-0.5 block text-muted-foreground">
                  {e.p_value != null
                    ? `p = ${e.p_value < 0.001 ? "<0.001" : e.p_value.toFixed(3)}`
                    : "p —"}
                </span>
              </>
            }
          />
        </div>

        <div className="rounded-md border border-border/70 bg-muted/20 px-3 py-2.5">
          <div className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            Baseline vs current
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            {e.baseline_summary}
          </p>
          <p className="mt-1 text-[12px] leading-relaxed text-foreground">
            {e.current_summary}
          </p>
        </div>
      </div>

      <div className="min-w-0 overflow-hidden rounded-md border border-border/70 bg-muted/15 p-3">
        <div className="mb-2 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Distribution
        </div>
        <EvidenceShape e={e} />
      </div>
    </div>
  )
}

function Metric({
  label,
  value,
  mono = true,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 text-[13px] leading-snug",
          mono && "font-mono tabular-nums",
        )}
      >
        {value}
      </div>
    </div>
  )
}

function formatStat(n: number) {
  return n >= 10 ? n.toFixed(1) : n.toFixed(2)
}

function ThresholdBar({
  statistic,
  threshold,
  flagged,
}: {
  statistic: number
  threshold: number
  flagged: boolean
}) {
  const max = Math.max(statistic, threshold) * 1.15 || 1
  const statPct = Math.min(100, (statistic / max) * 100)
  const thrPct = Math.min(100, (threshold / max) * 100)
  return (
    <div
      className="relative mt-1.5 h-2 w-full max-w-[140px] overflow-hidden rounded-sm bg-muted"
      title={`statistic ${formatStat(statistic)} vs threshold ${formatStat(threshold)}`}
    >
      <div
        className={cn(
          "absolute inset-y-0 left-0 rounded-sm",
          flagged ? "bg-destructive/80" : "bg-foreground/55",
        )}
        style={{ width: `${statPct}%` }}
      />
      <div
        className="absolute top-0 bottom-0 z-[1] w-0.5 bg-foreground"
        style={{ left: `calc(${thrPct}% - 1px)` }}
        aria-hidden
      />
    </div>
  )
}

function EvidenceShape({ e }: { e: FeatureEvidence }) {
  if (e.baseline_sketch && e.current_sketch) {
    return (
      <DualViolin
        baseline={e.baseline_sketch}
        current={e.current_sketch}
        unit="tokens"
      />
    )
  }
  if (e.baseline_tools && e.current_tools) {
    return (
      <MassCompare
        baseline={e.baseline_tools.map((t) => ({
          label: t.tool,
          mass: t.mass,
        }))}
        current={e.current_tools.map((t) => ({
          label: t.tool,
          mass: t.mass,
        }))}
      />
    )
  }
  if (e.baseline_clusters && e.current_clusters) {
    return (
      <MassCompare
        baseline={e.baseline_clusters.map((c) => ({
          label: c.cluster,
          mass: c.mass,
        }))}
        current={e.current_clusters.map((c) => ({
          label: c.cluster,
          mass: c.mass,
        }))}
      />
    )
  }
  if (
    e.baseline_trials != null &&
    e.current_trials != null &&
    e.baseline_successes != null &&
    e.current_successes != null
  ) {
    return (
      <BetaBinomialBars
        baselineSuccesses={e.baseline_successes}
        baselineTrials={e.baseline_trials}
        currentSuccesses={e.current_successes}
        currentTrials={e.current_trials}
      />
    )
  }
  return (
    <span className="text-[12px] text-muted-foreground">no shape payload</span>
  )
}

/** Quantile violin / ridge — shows skew instead of mean±std. */
export function DualViolin({
  baseline,
  current,
  unit,
  className,
}: {
  baseline: QuantileSketch
  current: QuantileSketch
  unit?: string
  className?: string
}) {
  const min = Math.min(baseline.p10, current.p10)
  const max = Math.max(baseline.p90, current.p90)
  const span = max - min || 1
  const pos = (v: number) => ((v - min) / span) * 100

  return (
    <div className={cn("w-full min-w-0 space-y-2", className)}>
      <ViolinRow label="base" sketch={baseline} pos={pos} tone="muted" />
      <ViolinRow label="now" sketch={current} pos={pos} tone="fg" />
      <div className="flex justify-between font-mono text-[10px] text-muted-foreground tabular-nums">
        <span>
          {Math.round(min)}
          {unit ? ` ${unit}` : ""}
        </span>
        <span>p50</span>
        <span>{Math.round(max)}</span>
      </div>
    </div>
  )
}

function ViolinRow({
  label,
  sketch,
  pos,
  tone,
}: {
  label: string
  sketch: QuantileSketch
  pos: (v: number) => number
  tone: "muted" | "fg"
}) {
  const left = pos(sketch.p10)
  const midL = pos(sketch.p25)
  const med = pos(sketch.p50)
  const midR = pos(sketch.p75)
  const right = pos(sketch.p90)
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="w-8 shrink-0 text-[10px] text-muted-foreground">
        {label}
      </span>
      <div className="relative h-4 min-w-0 flex-1 overflow-hidden rounded-sm bg-muted/60">
        <div
          className="absolute top-1/2 h-px -translate-y-1/2 bg-muted-foreground/50"
          style={{ left: `${left}%`, width: `${Math.max(0, right - left)}%` }}
        />
        <div
          className={cn(
            "absolute top-1 bottom-1 rounded-[2px]",
            tone === "fg" ? "bg-foreground/65" : "bg-muted-foreground/35",
          )}
          style={{
            left: `${midL}%`,
            width: `${Math.max(2, midR - midL)}%`,
          }}
        />
        <div
          className="absolute top-0.5 bottom-0.5 w-0.5 rounded-full bg-foreground"
          style={{ left: `calc(${med}% - 1px)` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
        {Math.round(sketch.p50)}
      </span>
    </div>
  )
}

export function MassCompare({
  baseline,
  current,
}: {
  baseline: { label: string; mass: number }[]
  current: { label: string; mass: number }[]
}) {
  const labels = [
    ...new Set([
      ...baseline.map((b) => b.label),
      ...current.map((c) => c.label),
    ]),
  ]
  const bMap = Object.fromEntries(baseline.map((b) => [b.label, b.mass]))
  const cMap = Object.fromEntries(current.map((c) => [c.label, c.mass]))

  return (
    <div className="w-full min-w-0 space-y-2.5">
      <div className="flex gap-3 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="size-1.5 rounded-sm bg-muted-foreground/50" />
          base
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="size-1.5 rounded-sm bg-foreground/70" />
          now
        </span>
      </div>
      {labels.map((label) => (
        <div key={label} className="min-w-0 space-y-1">
          <div className="truncate font-mono text-[11px] text-foreground">
            {label}
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <div className="h-2 overflow-hidden rounded-sm bg-muted">
              <div
                className="h-full bg-muted-foreground/55"
                style={{ width: `${(bMap[label] ?? 0) * 100}%` }}
              />
            </div>
            <div className="h-2 overflow-hidden rounded-sm bg-muted">
              <div
                className="h-full bg-foreground/75"
                style={{ width: `${(cMap[label] ?? 0) * 100}%` }}
              />
            </div>
          </div>
          <div className="flex justify-between font-mono text-[10px] text-muted-foreground tabular-nums">
            <span>{((bMap[label] ?? 0) * 100).toFixed(0)}%</span>
            <span>{((cMap[label] ?? 0) * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function BetaBinomialBars({
  baselineSuccesses,
  baselineTrials,
  currentSuccesses,
  currentTrials,
}: {
  baselineSuccesses: number
  baselineTrials: number
  currentSuccesses: number
  currentTrials: number
}) {
  const bErr = 1 - baselineSuccesses / baselineTrials
  const cErr = 1 - currentSuccesses / currentTrials
  return (
    <div className="w-full min-w-0 space-y-2.5 text-[11px]">
      <RateRow label="base err" rate={bErr} tone="muted" />
      <RateRow label="now err" rate={cErr} tone="fg" />
      <div className="font-mono text-[10px] text-muted-foreground tabular-nums">
        {baselineSuccesses}/{baselineTrials} → {currentSuccesses}/
        {currentTrials}
      </div>
    </div>
  )
}

function RateRow({
  label,
  rate,
  tone,
}: {
  label: string
  rate: number
  tone: "muted" | "fg"
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="w-14 shrink-0 text-muted-foreground">{label}</span>
      <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-sm bg-muted">
        <div
          className={cn(
            "h-full rounded-sm",
            tone === "fg" ? "bg-destructive/80" : "bg-muted-foreground/45",
          )}
          style={{ width: `${Math.min(100, rate * 100 * 8)}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right font-mono tabular-nums text-foreground">
        {(rate * 100).toFixed(1)}%
      </span>
    </div>
  )
}

export function ClusterStack({ masses }: { masses: ClusterMass[] }) {
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-sm bg-muted">
      {masses.map((m, i) => (
        <div
          key={m.cluster}
          className={cn(
            "h-full border-r border-background/30 last:border-r-0",
            ["bg-foreground/75", "bg-foreground/45", "bg-foreground/25"][i % 3],
          )}
          style={{ width: `${m.mass * 100}%` }}
          title={`${m.cluster} ${(m.mass * 100).toFixed(0)}%`}
        />
      ))}
    </div>
  )
}

/** Unused ToolMass export keep for typing consumers. */
export type { ToolMass }
