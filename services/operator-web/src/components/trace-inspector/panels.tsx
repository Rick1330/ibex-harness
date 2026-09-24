"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import Link from "next/link"

import { CopyId } from "@/components/explore/copy-id"
import { PaginationBar, usePagination } from "@/components/explore/pagination"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ASSEMBLY_TONES, VIZ } from "@/lib/explore/viz-colors"
import type {
  ContextAssembly,
  DirectiveContext,
  EvaluationLink,
  RoutingDecision,
  ToolCall,
} from "@/lib/explore/types"
import { cn } from "@/lib/utils"

export function ContextAssemblyPanel({ data }: { data: ContextAssembly }) {
  const spent = data.buckets.reduce((s, b) => s + b.used, 0)
  const toneOf = (label: string) => {
    const idx = data.buckets.findIndex((b) => b.label === label)
    return ASSEMBLY_TONES[Math.max(0, idx) % ASSEMBLY_TONES.length]
  }
  const ordered = data.buckets.slice().sort((a, b) => a.priority - b.priority)

  return (
    <Card id="assembly" className={panelClass}>
      <CardHeader className="border-b pb-4">
        <CardTitle>Context assembly</CardTitle>
        <CardDescription>
          Budget by injection priority · tool-schema + formatter tokens included
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="mb-3 flex h-3 overflow-hidden rounded-md border border-border/60 bg-muted/50">
          {ordered.map((b) => (
            <div
              key={b.label}
              className={cn(
                "h-full border-r border-background/40 last:border-r-0",
                VIZ[toneOf(b.label)].fill,
              )}
              style={{ width: `${(b.used / data.total_budget) * 100}%` }}
              title={`${b.label}: ${b.used}/${data.total_budget}`}
            />
          ))}
        </div>
        <ul className="flex flex-col gap-1.5 font-mono text-sm">
          {ordered.map((b) => (
            <li
              key={b.label}
              className="flex items-center justify-between gap-2"
            >
              <span className="inline-flex min-w-0 items-center gap-2">
                <span
                  className={cn(
                    "size-2.5 shrink-0 rounded-[2px]",
                    VIZ[toneOf(b.label)].swatch,
                  )}
                  aria-hidden
                />
                <span className="truncate">{b.label}</span>
              </span>
              <span className="tabular-nums text-muted-foreground">
                {b.used}/{data.total_budget}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 border-t pt-2 font-mono text-[12px] text-muted-foreground">
          tool-schema {data.tool_schema_tokens} · formatter{" "}
          {data.formatter_tokens} · spent {spent}/{data.total_budget}
        </div>
        {data.compression && (
          <p className="mt-2 font-mono text-[12px]">
            compression: {data.compression.memory_id} summarized (
            {data.compression.model}) {data.compression.tokens_before}→
            {data.compression.tokens_after}
          </p>
        )}
        <p className="mt-2 text-[11px] text-muted-foreground">
          Injection order: Directive → History → Memories (procedural → factual
          → preference → behavioral → episodic) → Tool schemas
        </p>
      </CardContent>
    </Card>
  )
}

export function DirectiveRoutingPanel({
  directive,
  routing,
}: {
  directive: DirectiveContext
  routing: RoutingDecision
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="border-b pb-4">
        <CardTitle>Directive + routing</CardTitle>
        <CardDescription>
          Version hash, rollout bucket, provider decision provenance
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 pt-4 text-sm">
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <span>
            Directive: v{directive.version} (
            <CopyId
              value={directive.hash}
              label="directive hash"
              className="inline"
            />
            )
          </span>
          {directive.version !== directive.current_active_version && (
            <Link
              href="#"
              className="text-muted-foreground underline-offset-2 hover:underline"
            >
              diff vs active v{directive.current_active_version}
            </Link>
          )}
          {directive.regression_test_status && (
            <span className="text-muted-foreground">
              regression:{" "}
              {directive.regression_test_status === "pass" ? "✓" : "✗"}
              {directive.scenarios_passed}/{directive.scenarios_total}
            </span>
          )}
        </div>
        {directive.rollout && (
          <p className="font-mono text-[12px] text-muted-foreground">
            rollout {directive.rollout.stages} · sticky bucket{" "}
            {directive.rollout.sticky_hash_bucket} → v
            {directive.rollout.resolved_version}
          </p>
        )}
        <p className="font-mono text-xs">
          Routing: primary={routing.primary_provider}/{routing.primary_model},
          fallback=
          {routing.fallback_chain.length
            ? routing.fallback_chain.join("→")
            : "none"}
          , breaker={routing.circuit_breaker}
        </p>
        <p className="text-[12px] text-muted-foreground">{routing.reason}</p>
      </CardContent>
    </Card>
  )
}

export function ToolsTimeline({ tools }: { tools: ToolCall[] }) {
  const pager = usePagination(tools, 4)

  return (
    <Card id="tools" className={panelClass}>
      <CardHeader className="border-b pb-4">
        <CardTitle>Tools ({tools.length})</CardTitle>
        <CardDescription>
          Sanitized args · idempotency · latency · retries
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <ul className="flex flex-col gap-0 px-4 pt-4">
          {pager.slice.map((t) => (
            <li
              key={t.idempotency_key}
              className="grid gap-1.5 border-b border-dashed py-3 first:pt-0 last:border-0"
            >
              <div className="flex flex-wrap items-center gap-2 font-mono text-sm">
                <span
                  className={cn(
                    "size-2 shrink-0 rounded-full",
                    t.status === "ok" ? VIZ.context.swatch : "bg-destructive",
                  )}
                  aria-hidden
                />
                <span className="font-medium">{t.tool_name}</span>
                <span
                  className={
                    t.status === "ok"
                      ? "text-muted-foreground"
                      : "text-destructive"
                  }
                >
                  {t.status}
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {t.latency_ms}ms · retries {t.retry_count}
                </span>
              </div>
              <div className="h-1.5 max-w-[12rem] overflow-hidden rounded-sm bg-muted">
                <div
                  className={cn("h-full rounded-sm", VIZ.tool.fill)}
                  style={{
                    width: `${Math.min(100, Math.max(6, t.latency_ms / 20))}%`,
                  }}
                />
              </div>
              <div className="font-mono text-[12px] text-muted-foreground">
                idempotency: {t.idempotency_key}
              </div>
              <pre className="overflow-x-auto rounded-md bg-muted/50 p-2.5 font-mono text-[12px]">
                {JSON.stringify(t.args_sanitized)}
              </pre>
              <div className="text-xs text-muted-foreground">
                {t.result_summary}
              </div>
            </li>
          ))}
        </ul>
        <PaginationBar
          page={pager.page}
          pageCount={pager.pageCount}
          total={pager.total}
          from={pager.from}
          to={pager.to}
          onPageChange={pager.setPage}
          label="tools"
        />
      </CardContent>
    </Card>
  )
}

export function EvaluationPanel({
  evaluation,
}: {
  evaluation?: EvaluationLink
}) {
  if (!evaluation) {
    return (
      <Card id="evaluation" className={`${panelClass} border-dashed`}>
        <CardContent className="px-4 py-6 text-sm text-muted-foreground">
          No evaluation link — this trace was not part of a directive regression
          run.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card id="evaluation" className={panelClass}>
      <CardHeader className="border-b pb-4">
        <CardTitle>Evaluation link</CardTitle>
        <CardDescription>
          Directive regression scenario · judge ≠ model under test
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1 pt-4 font-mono text-sm">
        <span>
          {evaluation.scenario_id} · {evaluation.mode} ·{" "}
          <span
            className={
              evaluation.result === "PASS"
                ? "text-foreground"
                : "text-destructive"
            }
          >
            {evaluation.result}
          </span>
        </span>
        <span className="text-muted-foreground">
          judge={evaluation.judge_model} (≠ model under test)
        </span>
        <p className="mt-1 font-sans text-sm text-muted-foreground">
          {evaluation.rationale}
        </p>
      </CardContent>
    </Card>
  )
}
