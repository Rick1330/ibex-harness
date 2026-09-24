"use client"

import * as React from "react"
import Link from "next/link"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { CopyId } from "@/components/explore/copy-id"
import { LifecycleBadge } from "@/components/sessions/status-badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { MemoryDetail, LineageEdge } from "@/lib/sessions/types"

export function MemoryDetailView({ memory }: { memory: MemoryDetail }) {
  const [showRaw, setShowRaw] = React.useState(false)
  const [lineageExtra, setLineageExtra] = React.useState(false)
  const visibleLineage = lineageExtra
    ? memory.lineage
    : memory.lineage.slice(0, 3)

  return (
    <div className="flex flex-col gap-3">
      {memory.embedding_mismatch && (
        <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
          Embedding version mismatch: retrieval used{" "}
          <span className="font-mono">
            {memory.embedding_model}@{memory.embedding_version}
          </span>,{" "}current config is{" "}
          <span className="font-mono">
            {memory.embedding_model}@{memory.current_embedding_version}
          </span>.{" "}Surfaced — not swallowed.
        </p>
      )}

      <Card className={panelClass}>
        <CardHeader className="gap-2 border-b px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="font-mono text-[13px] font-medium">
              <CopyId value={memory.memory_id} label="memory_id" />
            </CardTitle>
            <span className="font-mono text-[13px] text-muted-foreground">
              {memory.category}
            </span>
            <LifecycleBadge status={memory.lifecycle} />
          </div>
          <p className="text-[13px] leading-5">{memory.preview}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-muted-foreground">
            <span>confidence {memory.confidence.toFixed(2)}</span>
            <span>usefulness {memory.usefulness.toFixed(2)}</span>
            <span>visibility {memory.visibility}</span>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 px-4 py-3">
          {!showRaw ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowRaw(true)}
            >
              View raw content
            </Button>
          ) : (
            <pre className="overflow-x-auto rounded-md bg-muted/50 p-3 font-mono text-[13px] leading-5 whitespace-pre-wrap">
              {memory.content}
            </pre>
          )}
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardHeader className="gap-1 border-b px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Bounded lineage
          </CardTitle>
          <p className="text-[13px] text-muted-foreground">
            Depth-capped graph — not an unbounded traversal.
            {memory.lineage_truncated ? " More nodes available." : ""}
          </p>
        </CardHeader>
        <CardContent className="space-y-2 px-4 py-3 font-mono text-[13px] leading-5">
          {visibleLineage.map((e) => (
            <LineageRow
              key={`${e.kind}-${e.memory_id}-${e.direction}`}
              edge={e}
            />
          ))}
          {(memory.lineage_truncated || memory.lineage.length > 3) && (
            <Button
              size="sm"
              variant="ghost"
              className="mt-1"
              onClick={() => setLineageExtra((v) => !v)}
            >
              {lineageExtra ? "Collapse lineage" : "Load more lineage nodes ▾"}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardContent className="space-y-2 px-4 py-3 text-[13px] leading-5">
          <p>
            Retrieved in: {memory.retrieved_in_sessions} sessions · avg
            composite score {memory.avg_composite.toFixed(2)}
          </p>
          <p className="text-[13px] text-muted-foreground">
            {memory.retrieval_note}
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" variant="outline" asChild>
              <Link href={`/dashboard/sessions?q=memory:${memory.memory_id}`}>
                View sessions →
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function LineageRow({ edge }: { edge: LineageEdge }) {
  const arrow =
    edge.kind === "supersedes"
      ? edge.direction === "from"
        ? "supersedes ←"
        : "supersedes →"
      : edge.kind === "contradicts"
        ? edge.direction === "to"
          ? "contradicts →"
          : "contradicts ←"
        : edge.direction === "from"
          ? "specializes ←"
          : "specializes →"

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-muted-foreground">{arrow}</span>
      <Link
        href={`/dashboard/memories/${edge.memory_id}`}
        className="hover:underline"
      >
        {edge.memory_id}
      </Link>
      <LifecycleBadge status={edge.status} />
      {edge.at && (
        <span className="text-[13px] text-muted-foreground">{edge.at}</span>
      )}
      {edge.note && (
        <span className="text-[13px] text-amber-800 dark:text-amber-200">
          ({edge.note})
        </span>
      )}
    </div>
  )
}
