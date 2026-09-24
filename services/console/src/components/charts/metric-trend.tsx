"use client"

import type { ReactNode } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts"

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { cn } from "@/lib/utils"

/**
 * Fingerprint-history chart language — bordered metric panel, dashed
 * reference line, sparse dots for events, mono 10px ticks, 1.75px stroke.
 * Adopted across Overview / Billing / Analytics / Drift.
 */

const defaultConfig = {
  value: { label: "Value", color: "var(--foreground)" },
  secondary: { label: "Secondary", color: "var(--muted-foreground)" },
} satisfies ChartConfig

export type MetricTrendPoint = Record<
  string,
  string | number | boolean | null | undefined
>

export type MetricTrendMark = {
  x: string
  y: number
  tone?: "destructive" | "amber" | "foreground"
}

export function MetricTrend({
  title,
  data,
  dataKey = "value",
  secondaryKey,
  xKey = "t",
  baseline,
  baselineLabel = "baseline",
  referenceY,
  referenceYLabel,
  highlightX,
  marks,
  height = 140,
  yFormatter,
  className,
  config,
}: {
  title: string
  data: MetricTrendPoint[]
  dataKey?: string
  /** Optional dashed overlay series (e.g. expected / tokens). */
  secondaryKey?: string
  xKey?: string
  /** Horizontal dashed reference (baseline mean, etc.). */
  baseline?: number
  baselineLabel?: string
  /** Alternate horizontal rule (e.g. budget cap). */
  referenceY?: number
  referenceYLabel?: string
  /** Soft vertical band for a labeled window. */
  highlightX?: string
  marks?: MetricTrendMark[]
  height?: number
  yFormatter?: (v: number) => string
  className?: string
  config?: ChartConfig
}) {
  const chartConfig = config ?? defaultConfig
  const ruleY = referenceY ?? baseline
  const ruleLabel = referenceY != null ? referenceYLabel : baselineLabel

  return (
    <div
      className={cn(
        "rounded-md border border-border bg-card px-3 py-2 shadow-[0_1px_2px_oklch(0_0_0/0.04)] dark:shadow-none",
        className,
      )}
    >
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium text-muted-foreground">
          {title}
        </span>
        {baseline != null ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {baselineLabel}{" "}
            <span className="text-foreground">
              {yFormatter ? yFormatter(baseline) : baseline}
            </span>
          </span>
        ) : ruleY != null && ruleLabel ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {ruleLabel}{" "}
            <span className="text-foreground">
              {yFormatter ? yFormatter(ruleY) : ruleY}
            </span>
          </span>
        ) : null}
      </div>
      <ChartContainer
        config={chartConfig}
        className="aspect-auto! h-auto w-full"
        style={{ height }}
      >
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
        >
          <CartesianGrid vertical={false} strokeDasharray="2 6" />
          <XAxis
            dataKey={xKey}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={16}
            tick={{ fontSize: 10 }}
          />
          <YAxis
            width={44}
            tickLine={false}
            axisLine={false}
            tickMargin={6}
            tick={{ fontSize: 10 }}
            tickFormatter={
              yFormatter ? (v) => yFormatter(Number(v)) : (v) => String(v)
            }
          />
          <ChartTooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={<ChartTooltipContent indicator="line" />}
          />
          {ruleY != null ? (
            <ReferenceLine
              y={ruleY}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              ifOverflow="extendDomain"
              label={{
                value: ruleLabel ?? "",
                position: "insideTopRight",
                fill: "var(--muted-foreground)",
                fontSize: 9,
              }}
            />
          ) : null}
          {highlightX ? (
            <ReferenceArea
              x1={highlightX}
              x2={highlightX}
              strokeOpacity={0}
              fill="var(--chart-4)"
              fillOpacity={0.12}
            />
          ) : null}
          {secondaryKey ? (
            <Line
              type="monotone"
              dataKey={secondaryKey}
              name="secondary"
              stroke="var(--color-secondary)"
              strokeWidth={1.25}
              strokeDasharray="4 3"
              dot={false}
              activeDot={false}
            />
          ) : null}
          <Line
            type="monotone"
            dataKey={dataKey}
            name="value"
            stroke="var(--color-value)"
            strokeWidth={1.75}
            dot={false}
            activeDot={{ r: 3 }}
          />
          {marks?.map((m, i) => (
            <ReferenceDot
              key={`${m.x}-${i}`}
              x={m.x}
              y={m.y}
              r={4}
              fill={
                m.tone === "amber"
                  ? "oklch(0.75 0.15 75)"
                  : m.tone === "foreground"
                    ? "var(--foreground)"
                    : "var(--destructive)"
              }
              stroke="var(--background)"
              strokeWidth={2}
            />
          ))}
        </LineChart>
      </ChartContainer>
    </div>
  )
}

export function ChartLegendSwatch({
  className,
  label,
}: {
  className: string
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <span
        className={cn("inline-block size-2.5 rounded-sm border", className)}
        aria-hidden
      />
      {label}
    </span>
  )
}

export function MetricTrendGrid({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn("grid gap-4 md:grid-cols-2", className)}>{children}</div>
  )
}
