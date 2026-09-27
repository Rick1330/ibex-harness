import Link from "next/link"
import { cookies } from "next/headers"

import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fetchOperatorContext, fetchOperatorTraces } from "@/lib/api/d1"
import type { OperatorContext, OperatorTraceList } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"

async function load(): Promise<{ context: OperatorContext | null; traces: OperatorTraceList | null; error: string | null }> {
  const store = await cookies()
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = store.get(name)?.value
  const cookie = value ? `${name}=${value}` : undefined
  try {
    const [context, traces] = await Promise.all([
      fetchOperatorContext(cookie),
      fetchOperatorTraces(cookie, new URLSearchParams()),
    ])
    return { context, traces, error: null }
  } catch (error) {
    const message = error instanceof OperatorApiError && (error.status === 401 || error.status === 403)
      ? "Operator session is missing, expired, or lacks metadata-read permission. No preview data is shown."
      : "Trace metadata is unavailable. No mock values are substituted."
    return { context: null, traces: null, error: message }
  }
}

export async function LiveExplorePage() {
  const { context, traces, error } = await load()
  return (
    <DashboardShell liveMode operatorContext={context} showPreviewBanner={false}>
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">Explore</p>
              <h1 className="mt-2 font-serif text-4xl font-normal tracking-normal md:text-5xl">Trace metadata</h1>
              <p className="mt-2 text-sm text-muted-foreground">Global, tenant-scoped evidence snapshots · metadata-only D2</p>
            </div>
            <span className="rounded-full border px-2 py-1 font-mono text-[12px] text-muted-foreground">read-only · live</span>
          </div>
          {error ? <output className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">{error}</output> : null}
          {traces ? <TraceTable data={traces} /> : null}
        </div>
      </main>
    </DashboardShell>
  )
}

function TraceTable({ data }: Readonly<{ data: OperatorTraceList }>) {
  return (
    <Card className={`${panelClass} mt-4`}>
      <CardHeader>
        <CardTitle className="text-base">Traces ({data.items.length}{data.truncated ? "+" : ""})</CardTitle>
        <p className="text-sm text-muted-foreground">Source: {data.items[0]?.evidence.source ?? "postgres.evidence_runs"} · observed {new Date(data.observed_at).toISOString()}</p>
      </CardHeader>
      <CardContent className="overflow-x-auto px-0">
        <Table>
          <TableHeader><TableRow><TableHead scope="col">Trace</TableHead><TableHead scope="col">Request</TableHead><TableHead scope="col">Status</TableHead><TableHead scope="col">Started</TableHead><TableHead scope="col">Evidence</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.items.map((trace) => (
              <TableRow key={trace.run_id}>
                <TableCell className="font-mono"><Link className="underline-offset-4 hover:underline focus-visible:underline" href={`/dashboard/explore/t/${encodeURIComponent(trace.trace_id)}`}>{trace.trace_id}</Link></TableCell>
                <TableCell className="font-mono text-xs">{trace.request_id}</TableCell>
                <TableCell>{trace.status}{trace.error_code ? ` · ${trace.error_code}` : ""}</TableCell>
                <TableCell className="whitespace-nowrap text-xs">{new Date(trace.started_at).toISOString()}</TableCell>
                <TableCell className="text-xs">{trace.evidence.completeness} · {trace.evidence.freshness} · {trace.evidence.retention}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data.items.length === 0 ? <p className="px-4 py-8 text-center text-sm text-muted-foreground">No published trace metadata in this tenant and time window.</p> : null}
      </CardContent>
    </Card>
  )
}
