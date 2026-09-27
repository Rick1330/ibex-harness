import Link from "next/link"
import { cookies } from "next/headers"

import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { fetchOperatorContext, fetchOperatorTraceDetail } from "@/lib/api/d1"
import type { OperatorContext, OperatorTraceDetail } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"

async function load(traceId: string): Promise<{ context: OperatorContext | null; trace: OperatorTraceDetail | null; error: string | null }> {
  const store = await cookies()
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = store.get(name)?.value
  const cookie = value ? `${name}=${value}` : undefined
  try {
    const [context, trace] = await Promise.all([fetchOperatorContext(cookie), fetchOperatorTraceDetail(cookie, traceId)])
    return { context, trace, error: null }
  } catch (error) {
    const status = error instanceof OperatorApiError ? error.status : 0
    return { context: null, trace: null, error: status === 404 ? "Trace not found" : "Trace metadata is unavailable. No mock values are substituted." }
  }
}

export async function LiveTracePage({ traceId }: Readonly<{ traceId: string }>) {
  const { context, trace, error } = await load(traceId)
  return (
    <DashboardShell liveMode operatorContext={context} showPreviewBanner={false}>
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <Link className="text-sm text-muted-foreground underline-offset-4 hover:underline" href="/dashboard/explore">← Back to Explore</Link>
          {error ? <Card className={`${panelClass} mt-4`}><CardContent className="py-10 text-center"><h1 className="text-lg font-medium">{error}</h1><p className="mt-2 text-sm text-muted-foreground">Unknown or out-of-tenant IDs do not reveal whether another trace exists.</p></CardContent></Card> : null}
          {trace ? <TraceSnapshot trace={trace} /> : null}
        </div>
      </main>
    </DashboardShell>
  )
}

function TraceSnapshot({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Card className={`${panelClass} mt-4`}>
      <CardHeader>
        <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">Trace Inspector · frozen metadata snapshot</p>
        <CardTitle className="mt-2 break-all font-mono text-xl">{trace.trace_id}</CardTitle>
        <p className="text-sm text-muted-foreground">Source {trace.evidence.source} · observed {new Date(trace.evidence.observed_at).toISOString()} · watermark unavailable</p>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-4 md:grid-cols-2">
          <Metadata label="Request" value={trace.request_id} />
          <Metadata label="Run" value={trace.run_id} />
          <Metadata label="Status" value={trace.status} />
          <Metadata label="Started" value={new Date(trace.started_at).toISOString()} />
          <Metadata label="Ended" value={trace.ended_at ? new Date(trace.ended_at).toISOString() : "unavailable"} />
          <Metadata label="Measured duration" value={trace.duration_ms === null ? "unavailable" : `${trace.duration_ms} ms`} />
          <Metadata label="Completeness" value={trace.evidence.completeness} />
          <Metadata label="Retention" value={trace.evidence.retention} />
        </dl>
        <div className="md:col-span-2 rounded-md border border-dashed p-4">
          <h2 className="font-medium">Provenance sections unavailable</h2>
          <p className="mt-1 text-sm text-muted-foreground">P2 joins, P3 field policy, score schema, and content authorization are not complete for these sections. No transcript, tool arguments, raw JSON, score waterfall, replay, or actions are exposed.</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">{trace.unavailable_sections.join(" · ")}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function Metadata({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-all font-mono text-sm">{value}</dd></div>
}
