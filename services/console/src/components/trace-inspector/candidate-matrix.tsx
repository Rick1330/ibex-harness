"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"

import { DispositionBadge } from "@/components/explore/evidence-badges"
import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type {
  CandidateDisposition,
  RetrievalCandidate,
} from "@/lib/explore/types"
import { VIZ } from "@/lib/explore/viz-colors"
import { cn } from "@/lib/utils"

const DISPOSITIONS: CandidateDisposition[] = [
  "included",
  "budget_excluded",
  "filtered",
  "failed",
]

type SortKey =
  "retrieval_rank" | "similarity" | "final_rank" | "delta_rank" | "composite"

export function CandidateMatrix({
  candidates,
  selectedId,
  onSelect,
}: {
  candidates: RetrievalCandidate[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const [enabled, setEnabled] = React.useState<
    Record<CandidateDisposition, boolean>
  >({
    included: true,
    budget_excluded: true,
    filtered: true,
    failed: true,
  })
  const [sortKey, setSortKey] = React.useState<SortKey>("retrieval_rank")
  const [asc, setAsc] = React.useState(true)

  const rows = React.useMemo(() => {
    const filtered = candidates.filter((c) => enabled[c.disposition])
    return [...filtered].sort((a, b) => {
      const av = valueFor(a, sortKey)
      const bv = valueFor(b, sortKey)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return asc ? av - bv : bv - av
    })
  }, [asc, candidates, enabled, sortKey])

  const pager = usePagination(rows, 8)

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setAsc((v) => !v)
    else {
      setSortKey(key)
      setAsc(true)
    }
  }

  return (
    <Card id="candidate-matrix" className={panelClass}>
      <CardHeader className="border-b pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <div>
            <CardTitle>Candidate matrix</CardTitle>
            <CardDescription className="mt-1">
              Retrieval → composite re-rank · disposition is categorical
            </CardDescription>
          </div>
          <div className="ml-auto flex flex-wrap gap-1">
            {DISPOSITIONS.map((d) => (
              <Button
                key={d}
                type="button"
                size="xs"
                variant={enabled[d] ? "secondary" : "ghost"}
                className="font-mono text-[11px]"
                onClick={() =>
                  setEnabled((prev) => ({ ...prev, [d]: !prev[d] }))
                }
              >
                {d.replace("_", "-")}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <SortHead
                label="rank"
                active={sortKey === "retrieval_rank"}
                onClick={() => toggleSort("retrieval_rank")}
              />
              <SortHead
                label="sim"
                active={sortKey === "similarity"}
                onClick={() => toggleSort("similarity")}
              />
              <SortHead
                label="final"
                active={sortKey === "final_rank"}
                onClick={() => toggleSort("final_rank")}
              />
              <SortHead
                label="Δrank"
                active={sortKey === "delta_rank"}
                onClick={() => toggleSort("delta_rank")}
              />
              <TableHead className="h-11 px-3">cat</TableHead>
              <SortHead
                label="score"
                active={sortKey === "composite"}
                onClick={() => toggleSort("composite")}
              />
              <TableHead className="h-11 px-3">tok</TableHead>
              <TableHead className="h-11 px-3">disp</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pager.slice.map((c) => (
              <TableRow
                key={c.memory_id}
                data-state={selectedId === c.memory_id ? "selected" : undefined}
                className="cursor-pointer"
                onClick={() => onSelect(c.memory_id)}
              >
                <TableCell className="px-3 py-2.5 font-mono text-sm tabular-nums">
                  {c.retrieval_rank}
                </TableCell>
                <TableCell className="px-3 py-2.5 font-mono text-sm tabular-nums">
                  {c.similarity == null ? "—" : c.similarity.toFixed(2)}
                </TableCell>
                <TableCell className="px-3 py-2.5 font-mono text-sm tabular-nums">
                  {c.final_rank ?? "—"}
                </TableCell>
                <TableCell
                  className={cn(
                    "px-3 py-2.5 font-mono text-sm tabular-nums",
                    c.delta_rank != null &&
                      c.delta_rank > 0 &&
                      "text-foreground",
                    c.delta_rank != null &&
                      c.delta_rank < 0 &&
                      "text-destructive",
                  )}
                >
                  {c.delta_rank == null
                    ? "—"
                    : c.delta_rank > 0
                      ? `+${c.delta_rank}`
                      : c.delta_rank}
                </TableCell>
                <TableCell className="px-3 py-2.5 font-mono text-xs">
                  {c.category ? abbrev(c.category) : "—"}
                </TableCell>
                <TableCell className="px-3 py-2.5">
                  {c.score ? (
                    <div className="flex min-w-[4.5rem] flex-col gap-1">
                      <span className="font-mono text-sm tabular-nums">
                        {c.score.composite.toFixed(2)}
                      </span>
                      <div className="h-1.5 overflow-hidden rounded-sm bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-sm",
                            VIZ["score-a"].fill,
                          )}
                          style={{
                            width: `${Math.min(100, c.score.composite * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <span className="font-mono text-sm tabular-nums text-muted-foreground">
                      —
                    </span>
                  )}
                </TableCell>
                <TableCell className="px-3 py-2.5 font-mono text-sm tabular-nums text-muted-foreground">
                  {c.token_estimate ?? "—"}
                </TableCell>
                <TableCell className="px-3 py-2.5">
                  <div className="flex flex-col gap-1">
                    <DispositionBadge disposition={c.disposition} />
                    {c.edges?.map((e) => (
                      <span
                        key={`${e.kind}-${e.other_memory_id}`}
                        className={cn(
                          "font-mono text-[10px]",
                          e.status === "pending_review"
                            ? "text-amber-700 dark:text-amber-300"
                            : "text-muted-foreground",
                        )}
                      >
                        {e.kind} {e.other_memory_id}
                        {e.status === "pending_review"
                          ? " · pending_review"
                          : ""}
                      </span>
                    ))}
                    {c.error && (
                      <span className="font-mono text-[10px] text-destructive">
                        {c.error}
                      </span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <PaginationBar
          page={pager.page}
          pageCount={pager.pageCount}
          total={pager.total}
          from={pager.from}
          to={pager.to}
          onPageChange={pager.setPage}
          label="candidates"
        />
      </CardContent>
    </Card>
  )
}

function SortHead({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <TableHead className="h-11 px-3">
      <button
        type="button"
        className={cn(
          "font-medium hover:text-foreground",
          active ? "text-foreground" : "text-muted-foreground",
        )}
        onClick={onClick}
      >
        {label}
      </button>
    </TableHead>
  )
}

function valueFor(c: RetrievalCandidate, key: SortKey): number | null {
  switch (key) {
    case "retrieval_rank":
      return c.retrieval_rank
    case "similarity":
      return c.similarity
    case "final_rank":
      return c.final_rank
    case "delta_rank":
      return c.delta_rank
    case "composite":
      return c.score?.composite ?? null
  }
}

function abbrev(cat: string) {
  return (
    {
      procedural: "proc",
      factual: "fact",
      preference: "pref",
      behavioral: "behav",
      episodic: "epis",
    }[cat] ?? cat
  )
}
