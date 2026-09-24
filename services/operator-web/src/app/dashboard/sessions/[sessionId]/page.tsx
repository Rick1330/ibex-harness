"use client"

import * as React from "react"
import Link from "next/link"
import { useParams } from "next/navigation"

import { exploreTable } from "@/components/explore/table-styles"
import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { CascadePreviewPanel } from "@/components/sessions/cascade-preview"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { PrivilegedGateBanner } from "@/components/sessions/privileged-gate"
import { ReplaySandbox } from "@/components/sessions/replay-sandbox"
import { SessionTimeline } from "@/components/sessions/session-timeline"
import { JobStatusBadge } from "@/components/sessions/status-badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DELETE_PREVIEW,
  JOB_LIST,
  REPLAY_FIXTURE,
  SESSION_BY_ID,
} from "@/lib/sessions/fixtures"

export default function SessionDetailPage() {
  const params = useParams<{ sessionId: string }>()
  const session = SESSION_BY_ID[params.sessionId]
  const jobs = usePagination(JOB_LIST, 10)

  return (
    <DashboardShell>
      <div className={pagePad}>
        {!session ? (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Session not found</div>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Unknown or out-of-org{" "}
                <span className="font-mono">{params.sessionId}</span> returns
                empty / 404 — never &quot;found but forbidden.&quot;
              </p>
              <Button asChild size="sm" className="mt-3">
                <Link href="/dashboard/sessions">Back to Sessions</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <Button asChild size="sm" variant="ghost" className="-ml-2">
                <Link href="/dashboard/sessions">← Sessions</Link>
              </Button>
            </div>

            <PrivilegedGateBanner />
            <SessionTimeline session={session} />

            <div className="grid items-start gap-3 lg:grid-cols-2">
              <CascadePreviewPanel preview={DELETE_PREVIEW} />
              <ReplaySandbox state={REPLAY_FIXTURE} />
            </div>

            <Card id="jobs" className={panelClass}>
              <CardHeader className="gap-1 border-b px-4 py-3">
                <CardTitle className="text-[13px] font-medium">
                  Governed jobs
                </CardTitle>
                <p className="text-[13px] text-muted-foreground">
                  Status includes parked — matches rollback: queued jobs drain
                  or park safely. Receipts are per-store, never a bare success.
                </p>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className={exploreTable.head}>
                        job_id
                      </TableHead>
                      <TableHead className={exploreTable.head}>kind</TableHead>
                      <TableHead className={exploreTable.head}>
                        target
                      </TableHead>
                      <TableHead className={exploreTable.head}>
                        status
                      </TableHead>
                      <TableHead className={exploreTable.head}>
                        receipt
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.slice.map((j) => (
                      <TableRow key={j.job_id}>
                        <TableCell
                          className={`${exploreTable.cell} ${exploreTable.mono}`}
                        >
                          {j.job_id}
                        </TableCell>
                        <TableCell
                          className={`${exploreTable.cell} ${exploreTable.mono}`}
                        >
                          {j.kind}
                        </TableCell>
                        <TableCell
                          className={`${exploreTable.cell} ${exploreTable.mono}`}
                        >
                          {j.target_id}
                        </TableCell>
                        <TableCell className={exploreTable.cell}>
                          <JobStatusBadge status={j.status} />
                        </TableCell>
                        <TableCell
                          className={`${exploreTable.cell} ${exploreTable.meta}`}
                        >
                          {j.receipts
                            ? j.receipts
                                .map((r) => `${r.store}:${r.status}`)
                                .join(" · ")
                            : (j.error ?? "—")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <PaginationBar
                  page={jobs.page}
                  pageCount={jobs.pageCount}
                  total={jobs.total}
                  from={jobs.from}
                  to={jobs.to}
                  onPageChange={jobs.setPage}
                  label="jobs"
                />
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </DashboardShell>
  )
}
