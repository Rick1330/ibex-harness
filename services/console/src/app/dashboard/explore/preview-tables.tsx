"use client"

import { useRouter } from "next/navigation"

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
import { FAILURE_LIST, SESSION_LIST } from "@/lib/explore/fixtures"
import { cn } from "@/lib/utils"

function sessionStatusTone(status: string): "ok" | "error" | "warn" {
  if (status === "success") return "ok"
  if (status === "error") return "error"
  return "warn"
}

export function SessionsTable() {
  const pager = usePagination(SESSION_LIST, 12, "accumulate")
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Session</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Model</TableHead>
            <TableHead className={listTable.head}>Traces</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Last active
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.slice.map((session) => (
            <TableRow key={session.session_id} className={listTable.row}>
              <TableCell className={cn(listTable.cell, listTable.primary)}>
                {session.session_id}
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot
                  tone={sessionStatusTone(session.status)}
                  label={session.status}
                />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {session.agent}
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {session.model}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {session.trace_count}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {session.last_active}
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
        label="sessions"
        variant="load-more"
      />
    </div>
  )
}

export function FailuresTable() {
  const router = useRouter()
  const pager = usePagination(FAILURE_LIST, 12, "accumulate")
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Failure</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Model</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Started
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.slice.map((failure) => (
            <TableRow
              key={failure.trace_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => {
                router.push(`/dashboard/explore/t/${failure.trace_id}`)
              }}
            >
              <TableCell className={cn(listTable.cell, "max-w-[280px]")}>
                <div className={listTable.primary}>{failure.trace_id}</div>
                <div className={cn(listTable.meta, "mt-0.5 text-destructive")}>
                  {failure.error}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone="error" label="error" />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {failure.agent}
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {failure.model}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {failure.started_at}
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
        label="failures"
        variant="load-more"
      />
    </div>
  )
}
