"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"
import Link from "next/link"
import {
  IconArrowLeft,
  IconLock,
  IconPlayerPlay,
  IconLink,
} from "@tabler/icons-react"
import { toast } from "sonner"

import { CopyId } from "@/components/explore/copy-id"
import { EvidenceBadgeRow } from "@/components/explore/evidence-badges"
import { Button } from "@/components/ui/button"
import { CandidateMatrix } from "@/components/trace-inspector/candidate-matrix"
import {
  ExplainTree,
  SchemaBadge,
} from "@/components/trace-inspector/explain-tree"
import { FlameGraph } from "@/components/trace-inspector/flame-graph"
import {
  ContextAssemblyPanel,
  DirectiveRoutingPanel,
  EvaluationPanel,
  ToolsTimeline,
} from "@/components/trace-inspector/panels"
import { allowsFullWaterfall } from "@/lib/explore/fixtures"
import type { TraceDetail } from "@/lib/explore/types"
import { VIZ, type VizTone } from "@/lib/explore/viz-colors"
import { cn } from "@/lib/utils"

export function TraceInspector({
  trace,
  returnHref = "/dashboard/explore",
}: {
  trace: TraceDetail
  returnHref?: string
}) {
  const [selectedMemory, setSelectedMemory] = React.useState(
    trace.candidates.find((c) => c.disposition === "included")?.memory_id ??
      trace.candidates[0]?.memory_id ??
      null,
  )
  const [replaySimulated, setReplaySimulated] = React.useState(false)
  const [rawUnlocked, setRawUnlocked] = React.useState(false)

  const selected =
    trace.candidates.find((c) => c.memory_id === selectedMemory) ?? null

  const totalMs = Object.values(trace.latency_full).reduce((a, b) => a + b, 0)
  const fullOk = allowsFullWaterfall(trace.score_schema)

  const scrollTo = (id: string) => {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  const onEvidence = (ref: string) => {
    if (ref === "matrix") scrollTo("candidate-matrix")
    else if (ref === "assembly") scrollTo("assembly")
    else if (ref === "tools") scrollTo("tools")
    else if (ref === "evaluation") scrollTo("evaluation")
  }

  const copyTraceLink = async () => {
    const url = `${window.location.origin}/dashboard/explore/t/${trace.trace_id}`
    await navigator.clipboard.writeText(url)
    toast.success("Copied trace link")
  }

  const requestRaw = () => {
    // Design target: raw:read + recent auth + audit event — not a UI toggle.
    toast.message("raw:read + recent authentication required", {
      description:
        "Access would emit an audit event. Mock unlock for design preview only.",
    })
    setRawUnlocked(true)
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 py-4 md:gap-5 md:py-6 lg:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="ghost" className="-ml-2">
          <Link href={returnHref}>
            <IconArrowLeft className="size-4" />
            Explore
          </Link>
        </Button>
        <SchemaBadge schema={trace.score_schema} />
        {replaySimulated && (
          <span className="rounded-full border border-amber-600/40 px-2 py-0.5 font-mono text-[11px] text-amber-800 dark:text-amber-300">
            evidence:simulated (replay)
          </span>
        )}
      </div>

      {/* Layer 1 — sticky summary strip */}
      <header
        className={`sticky top-0 z-10 flex flex-col gap-3 ${panelClass} bg-card/95 p-4 backdrop-blur supports-backdrop-filter:bg-card/80`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <CopyId
                value={trace.trace_id}
                label="trace_id"
                className="text-base font-medium"
              />
              <span className="text-sm text-muted-foreground">
                {trace.org} / {trace.agent} / {trace.session_id}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <PivotChip href="#" label={trace.agent} />
              <PivotChip href="#" label={trace.session_id} />
              <PivotChip href="#" label={trace.model} />
              <PivotChip href="#" label={trace.provider} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setReplaySimulated(true)
                toast.success("Replay started in sandbox", {
                  description:
                    "Immutable snapshot — does not mutate original trace or live state.",
                })
              }}
            >
              <IconPlayerPlay className="size-3.5" />
              Replay ▸
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void copyTraceLink()}
            >
              <IconLink className="size-3.5" />
              Copy trace link
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[13px] text-muted-foreground">
          <span>
            {trace.tokens.total.toLocaleString()} tokens ({trace.tokens.prompt}/
            {trace.tokens.completion})
          </span>
          <span>{totalMs.toLocaleString()}ms total</span>
        </div>

        <LatencyBreakdown stages={trace.latency_full} />

        <EvidenceBadgeRow
          evidence={
            replaySimulated
              ? { ...trace.evidence, completeness: "simulated" }
              : trace.evidence
          }
        />

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 font-mono text-[12px]">
          <span className="text-muted-foreground">repro:</span>
          <CopyableInline
            label={`tokenizer ${trace.reproducibility.tokenizer_version}`}
            value={trace.reproducibility.tokenizer_version}
          />
          <CopyableInline
            label={`packer ${trace.reproducibility.packing_policy_version}`}
            value={trace.reproducibility.packing_policy_version}
          />
          <CopyableInline
            label={`half-life ${trace.reproducibility.half_life_table_version}`}
            value={trace.reproducibility.half_life_table_version}
          />
          <CopyableInline
            label={`directive#${trace.reproducibility.directive_version}(${trace.reproducibility.directive_hash})`}
            value={`${trace.reproducibility.directive_version}:${trace.reproducibility.directive_hash}`}
          />
        </div>
      </header>

      <FlameGraph
        root={trace.spans[0]}
        totalMs={totalMs}
        onSelectEvidence={onEvidence}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <CandidateMatrix
          candidates={trace.candidates}
          selectedId={selectedMemory}
          onSelect={setSelectedMemory}
        />
        <ContextAssemblyPanel data={trace.context_assembly} />
      </div>

      <ExplainTree
        score={selected?.score ?? null}
        scoreSchema={trace.score_schema}
        candidateLabel={
          selected
            ? `#${selected.retrieval_rank} (${selected.memory_id})`
            : "none"
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ToolsTimeline tools={trace.tools} />
        <div className="flex flex-col gap-4">
          <DirectiveRoutingPanel
            directive={trace.directive}
            routing={trace.routing}
          />
          <EvaluationPanel evaluation={trace.evaluation} />
        </div>
      </div>

      {/* Raw / pivots */}
      <section className={`${panelClass} p-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={requestRaw}
            disabled={!trace.raw_available}
          >
            <IconLock className="size-3.5" />
            View raw JSON — requires raw:read + recent auth
          </Button>
          <div className="ml-auto flex flex-wrap gap-3 font-mono text-[12px] text-muted-foreground">
            <CopyId value={trace.request_id} label="request_id" />
            <CopyId value={trace.checkpoint_id} label="checkpoint_id" />
            <CopyId value={trace.session_id} label="session_id" />
          </div>
        </div>
        {rawUnlocked && (
          <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-muted/50 p-3 font-mono text-[11px]">
            {JSON.stringify(
              {
                trace_id: trace.trace_id,
                score_schema: trace.score_schema,
                reproducibility: trace.reproducibility,
                candidates: trace.candidates.map((c) => ({
                  memory_id: c.memory_id,
                  disposition: c.disposition,
                  score: c.score,
                })),
              },
              null,
              2,
            )}
          </pre>
        )}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
          <span>pivots:</span>
          <Link href="#" className="hover:underline">
            session → agent
          </Link>
          <Link href="#" className="hover:underline">
            memories used → lineage
          </Link>
          <Link href="#" className="hover:underline">
            directive v{trace.directive.version} → sessions
          </Link>
          <span title="Phase 4.5 producer contract">
            drift alert → contributing traces (pending)
          </span>
        </div>
      </section>

      <p className="text-[12px] text-muted-foreground">
        Design target (4.D.2 finished). Fixture uses{" "}
        <span className="font-mono">score_schema:{trace.score_schema}</span>
        {fullOk
          ? " — five-term waterfall active."
          : " — waterfall refused for interim payloads."}{" "}
        Not wired to live data.
      </p>
    </div>
  )
}

function PivotChip({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="rounded-full border bg-muted/50 px-2.5 py-0.5 font-mono text-[12px] hover:bg-muted"
      title="Preserves return link back to this trace"
    >
      {label}
    </Link>
  )
}

function CopyableInline({ label, value }: { label: string; value: string }) {
  return (
    <button
      type="button"
      className={cn("hover:underline")}
      onClick={async () => {
        await navigator.clipboard.writeText(value)
        toast.success("Copied")
      }}
    >
      {label}
    </button>
  )
}

function LatencyBreakdown({ stages }: { stages: TraceDetail["latency_full"] }) {
  const items: { label: string; ms: number; tone: VizTone }[] = [
    { label: "auth validation", ms: stages.auth_ms, tone: "auth" },
    { label: "rate limit", ms: stages.rate_limit_ms, tone: "auth" },
    {
      label: "context retrieve",
      ms: stages.context_retrieve_ms,
      tone: "context",
    },
    { label: "context rank", ms: stages.context_rank_ms, tone: "context" },
    { label: "context pack", ms: stages.context_pack_ms, tone: "stream" },
    { label: "provider call", ms: stages.provider_ms, tone: "provider" },
    { label: "streaming", ms: stages.stream_ms, tone: "tool" },
  ]
  const total = items.reduce((s, i) => s + i.ms, 0) || 1

  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-3 overflow-hidden rounded-md border border-border/60 bg-muted/50">
        {items.map((item) =>
          item.ms <= 0 ? null : (
            <div
              key={item.label}
              className={cn(
                "h-full border-r border-background/40 last:border-r-0",
                VIZ[item.tone].fill,
              )}
              style={{ width: `${(item.ms / total) * 100}%` }}
              title={`${item.label}: ${item.ms}ms`}
            />
          ),
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1.5 font-mono text-[11px] text-muted-foreground">
        {items.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1.5">
            <span
              className={cn(
                "size-2 shrink-0 rounded-[2px]",
                VIZ[item.tone].swatch,
              )}
              aria-hidden
            />
            {item.label}{" "}
            <span className="tabular-nums text-foreground">{item.ms}ms</span>
          </span>
        ))}
      </div>
    </div>
  )
}
