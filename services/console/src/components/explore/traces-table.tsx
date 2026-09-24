"use client"

import Link from "next/link"

import { CopyId } from "@/components/explore/copy-id"
import { EvidenceBadgeRow } from "@/components/explore/evidence-badges"
import { LatencyMiniBar } from "@/components/explore/latency-bar"
import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { listTable } from "@/components/explore/table-styles"
import { StatusDot } from "@/components/list/status-dot"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { TraceListItem, TraceStatus } from "@/lib/explore/types"
import { cn } from "@/lib/utils"

function statusTone(status: TraceStatus): "ok" | "error" | "warn" {
  if (status === "success") return "ok"
  if (status === "error") return "error"
  return "warn"
}

export function TracesTable({
  rows,
  selectedId,
  hoveredId,
  onHover,
  onSelect,
}: {
  rows: TraceListItem[]
  selectedId?: string | null
  hoveredId?: string | null
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}) {
  const pager = usePagination(rows, 12, "accumulate")

  if (rows.length === 0) {
    return (
      <div className="px-1 py-10 text-center text-[13px] text-muted-foreground">
        No traces in this result set. Cross-tenant lookups return empty / 404 —
        never a &quot;found but forbidden&quot; signal.
      </div>
    )
  }

  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Trace</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Model</TableHead>
            <TableHead className={listTable.head}>Latency</TableHead>
            <TableHead className={listTable.head}>Tokens</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Evidence
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.slice.map((row) => {
            const active =
              row.trace_id === selectedId || row.trace_id === hoveredId
            return (
              <TableRow
                key={row.trace_id}
                data-state={active ? "selected" : undefined}
                className={cn(listTable.row, "cursor-pointer")}
                onMouseEnter={() => onHover(row.trace_id)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(row.trace_id)}
              >
                <TableCell className={cn(listTable.cell, "max-w-[220px]")}>
                  <Link
                    href={`/dashboard/explore/t/${row.trace_id}`}
                    className="block min-w-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <CopyId
                      value={row.trace_id}
                      label="trace_id"
                      className={listTable.primary}
                    />
                    <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                      {row.session_id}
                    </div>
                  </Link>
                </TableCell>
                <TableCell className={listTable.cell}>
                  <StatusDot
                    tone={statusTone(row.status)}
                    label={row.status}
                    detail={`${row.latency.total_ms}ms`}
                  />
                </TableCell>
                <TableCell className={cn(listTable.cell, listTable.mono)}>
                  {row.agent}
                </TableCell>
                <TableCell className={cn(listTable.cell, listTable.mono)}>
                  <span className="text-foreground">{row.model}</span>
                  <span className={listTable.meta}> · {row.provider}</span>
                </TableCell>
                <TableCell className={listTable.cell}>
                  <LatencyMiniBar
                    auth_ms={row.latency.auth_ms}
                    context_ms={row.latency.context_retrieve_ms}
                    provider_ms={row.latency.provider_ms}
                    stream_ms={row.latency.stream_ms}
                    total_ms={row.latency.total_ms}
                  />
                </TableCell>
                <TableCell
                  className={cn(listTable.cell, listTable.mono, listTable.meta)}
                >
                  {row.tokens.prompt.toLocaleString()}/
                  {row.tokens.completion.toLocaleString()}
                </TableCell>
                <TableCell className={cn(listTable.cell, "text-right")}>
                  <EvidenceBadgeRow evidence={row.evidence} compact />
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <PaginationBar
        page={pager.page}
        pageCount={pager.pageCount}
        total={pager.total}
        from={pager.from}
        to={pager.to}
        onPageChange={pager.setPage}
        label="traces"
        variant="load-more"
      />
    </div>
  )
}
