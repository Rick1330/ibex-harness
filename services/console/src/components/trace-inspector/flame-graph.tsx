"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import { spanTone, VIZ, type VizTone } from "@/lib/explore/viz-colors"
import type { SpanNode } from "@/lib/explore/types"
import { cn } from "@/lib/utils"

const LEGEND: VizTone[] = [
  "root",
  "auth",
  "context",
  "provider",
  "tool",
  "stream",
  "eval",
]

export function FlameGraph({
  root,
  totalMs,
  onSelectEvidence,
}: {
  root: SpanNode
  totalMs: number
  onSelectEvidence?: (ref: string) => void
}) {
  const spans = flatten(root)
  const maxDepth = spans.reduce((m, s) => Math.max(m, s.depth), 0)
  const trackH = Math.max(28, (maxDepth + 1) * 26 + 12)

  return (
    <section id="timeline" className={`${panelClass} p-4`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">Timeline / flame graph</h3>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Nested spans · click a bar with evidence to jump
          </p>
        </div>
        <span className="font-mono text-[12px] text-muted-foreground tabular-nums">
          {totalMs.toLocaleString()}ms
        </span>
      </div>

      <div
        className="relative overflow-hidden rounded-md border border-border/80 bg-muted/50"
        style={{ height: trackH }}
      >
        {/* Time grid */}
        {[0.25, 0.5, 0.75].map((f) => (
          <div
            key={f}
            className="pointer-events-none absolute inset-y-0 w-px bg-border/70"
            style={{ left: `${f * 100}%` }}
            aria-hidden
          />
        ))}
        {spans.map((s, i) => {
          const left = (s.start_ms / totalMs) * 100
          const width = Math.max(0.6, (s.duration_ms / totalMs) * 100)
          const top = s.depth * 26 + 8
          const tone = spanTone(s.name)
          const viz = VIZ[tone]
          return (
            <button
              key={s.span_id}
              type="button"
              title={`${s.name} · ${s.duration_ms}ms · depth ${s.depth}`}
              className={cn(
                "absolute h-5 overflow-hidden rounded-sm border border-black/10 px-1.5 font-mono text-[10px] font-medium shadow-sm transition-[filter,transform] dark:border-white/15",
                viz.fill,
                viz.text,
                s.evidence_ref
                  ? "cursor-pointer hover:brightness-110 hover:ring-1 hover:ring-foreground/30"
                  : "cursor-default",
              )}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                top,
                zIndex: 20 - s.depth,
                animationDelay: `${i * 28}ms`,
              }}
              onClick={() =>
                s.evidence_ref && onSelectEvidence?.(s.evidence_ref)
              }
            >
              <span className="block truncate">{s.name}</span>
            </button>
          )
        })}
      </div>

      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5">
        {LEGEND.map((tone) => (
          <span
            key={tone}
            className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground"
          >
            <span
              className={cn(
                "size-2.5 shrink-0 rounded-[2px]",
                VIZ[tone].swatch,
              )}
              aria-hidden
            />
            {VIZ[tone].label}
          </span>
        ))}
      </div>

      <div className="mt-2 flex justify-between font-mono text-[10px] text-muted-foreground tabular-nums">
        <span>0ms</span>
        <span>{Math.round(totalMs / 2)}ms</span>
        <span>{totalMs.toLocaleString()}ms</span>
      </div>
    </section>
  )
}

function flatten(node: SpanNode, depth = 0): (SpanNode & { depth: number })[] {
  const self = { ...node, depth }
  const kids = (node.children ?? []).flatMap((c) => flatten(c, depth + 1))
  return [self, ...kids]
}
