import Link from "next/link"
import { cookies } from "next/headers"

import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fetchOperatorContext, fetchOperatorTraces } from "@/lib/api/d1"
import type { OperatorContext, OperatorTraceList } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"
import {
  LiveExploreQueryError,
  liveExploreHref,
  parseLiveExploreQuery,
  serializeLiveExploreQuery,
  type LiveExploreQuery,
} from "@/lib/explore/live-query"

type SearchParams = Record<string, string | string[] | undefined>

async function load(searchParams: SearchParams): Promise<{
  context: OperatorContext | null
  traces: OperatorTraceList | null
  query: LiveExploreQuery | null
  error: string | null
  contextError: string | null
}> {
  let query: LiveExploreQuery
  try {
    query = parseLiveExploreQuery(searchParams)
  } catch (error) {
    const message = error instanceof LiveExploreQueryError ? error.message : "Invalid Explore query"
    return { context: null, traces: null, query: null, error: message, contextError: null }
  }

  const store = await cookies()
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = store.get(name)?.value
  const cookie = value ? `${name}=${value}` : undefined
  const apiQuery = serializeLiveExploreQuery(query)

  const [contextResult, tracesResult] = await Promise.allSettled([
    fetchOperatorContext(cookie),
    fetchOperatorTraces(cookie, apiQuery),
  ])

  let context: OperatorContext | null = null
  let contextError: string | null = null
  if (contextResult.status === "fulfilled") context = contextResult.value
  else {
    const err = contextResult.reason
    contextError =
      err instanceof OperatorApiError && (err.status === 401 || err.status === 403)
        ? "Operator context unavailable (session or permission)."
        : "Operator context unavailable."
  }

  if (tracesResult.status === "fulfilled") {
    return { context, traces: tracesResult.value, query, error: null, contextError }
  }
  const err = tracesResult.reason
  const message =
    err instanceof OperatorApiError && (err.status === 401 || err.status === 403)
      ? "Operator session is missing, expired, or lacks metadata-read permission. No preview data is shown."
      : "Trace metadata is unavailable. No mock values are substituted."
  return { context, traces: null, query, error: message, contextError }
}

export async function LiveExplorePage({
  searchParams,
}: Readonly<{ searchParams?: Promise<SearchParams> | SearchParams }>) {
  const resolved = searchParams instanceof Promise ? await searchParams : (searchParams ?? {})
  const { context, traces, query, error, contextError } = await load(resolved)
  return (
    <DashboardShell liveMode operatorContext={context} showPreviewBanner={false}>
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">Explore</p>
              <h1 className="mt-2 font-serif text-4xl font-normal tracking-normal md:text-5xl">Trace metadata</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Global, tenant-scoped evidence snapshots · metadata-only D2 · query grammar operator.trace-query.v1
              </p>
            </div>
            <span className="rounded-full border px-2 py-1 font-mono text-[12px] text-muted-foreground">read-only · live</span>
          </div>

          <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Explore result types">
            <span className="rounded-md border bg-muted px-3 py-1 text-sm" role="tab" aria-selected="true">
              Traces
            </span>
            <span className="rounded-md border border-dashed px-3 py-1 text-sm text-muted-foreground" role="tab" aria-disabled="true" title="Deferred until canonical session result types exist">
              Sessions (deferred)
            </span>
            <span className="rounded-md border border-dashed px-3 py-1 text-sm text-muted-foreground" role="tab" aria-disabled="true" title="Deferred until canonical failure result types exist">
              Failures (deferred)
            </span>
          </div>

          <div className="sr-only" aria-live="polite">
            {error ?? (traces ? `Loaded ${traces.returned_count} traces` : "Loading traces")}
          </div>

          {contextError ? (
            <output className="mt-4 block rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">{contextError}</output>
          ) : null}
          {error ? <output className="mt-4 block rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">{error}</output> : null}
          {traces && query ? <TraceTable data={traces} query={query} /> : null}
        </div>
      </main>
    </DashboardShell>
  )
}

function TraceTable({ data, query }: Readonly<{ data: OperatorTraceList; query: LiveExploreQuery }>) {
  const returnHref = liveExploreHref(query, { dropCursor: true })
  const nextHref =
    data.next_cursor && data.truncated
      ? liveExploreHref({ ...query, cursor: data.next_cursor })
      : null
  return (
    <Card className={`${panelClass} mt-4`}>
      <CardHeader>
        <CardTitle className="text-base">
          Traces ({data.returned_count}
          {data.matched_count != null ? ` of ${data.matched_count}` : ""}
          {data.truncated ? "+" : ""})
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Source: {data.items[0]?.evidence.source ?? "postgres.evidence_runs"} · observed{" "}
          {new Date(data.observed_at).toISOString()} · window {new Date(data.query_start).toISOString()} →{" "}
          {new Date(data.query_end).toISOString()}
        </p>
      </CardHeader>
      <CardContent className="overflow-x-auto px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Run</TableHead>
              <TableHead scope="col">Trace</TableHead>
              <TableHead scope="col">Status</TableHead>
              <TableHead scope="col">Publication</TableHead>
              <TableHead scope="col">Evidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((trace) => (
              <TableRow key={trace.run_id}>
                <TableCell className="font-mono text-xs">
                  <Link
                    className="underline-offset-4 hover:underline focus-visible:underline"
                    href={`/dashboard/explore/r/${encodeURIComponent(trace.run_id)}?return=${encodeURIComponent(returnHref)}`}
                  >
                    {trace.run_id}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  <Link
                    className="underline-offset-4 hover:underline focus-visible:underline"
                    href={`/dashboard/explore/t/${encodeURIComponent(trace.trace_id)}?return=${encodeURIComponent(returnHref)}`}
                  >
                    {trace.trace_id}
                  </Link>
                </TableCell>
                <TableCell>
                  {trace.status}
                  {trace.error_code ? ` · ${trace.error_code}` : ""}
                </TableCell>
                <TableCell className="text-xs">
                  {trace.evidence.publication_state} · {trace.evidence.source_watermark}
                </TableCell>
                <TableCell className="text-xs">
                  {trace.evidence.completeness} · {trace.evidence.freshness} · {trace.evidence.retention}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data.items.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            No published trace metadata in this tenant and time window.
          </p>
        ) : null}
        {nextHref ? (
          <div className="border-t px-4 py-3">
            <Link className="text-sm underline-offset-4 hover:underline" href={nextHref}>
              Load more
            </Link>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
