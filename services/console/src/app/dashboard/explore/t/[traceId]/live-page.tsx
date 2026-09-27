import Link from "next/link"
import { cookies } from "next/headers"

import { CopyId } from "@/components/explore/copy-id"
import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { fetchOperatorContext, fetchOperatorTraceResource } from "@/lib/api/d1"
import type { OperatorContext, OperatorTraceList } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"
import { safeExploreReturnHref } from "@/lib/explore/safe-return"

async function load(
  traceId: string,
): Promise<{ context: OperatorContext | null; runs: OperatorTraceList | null; error: string | null }> {
  const store = await cookies()
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = store.get(name)?.value
  const cookie = value ? `${name}=${value}` : undefined
  const [contextResult, runsResult] = await Promise.allSettled([
    fetchOperatorContext(cookie),
    fetchOperatorTraceResource("runs", cookie, traceId),
  ])
  const context = contextResult.status === "fulfilled" ? contextResult.value : null
  if (runsResult.status === "fulfilled") {
    return { context, runs: runsResult.value, error: null }
  }
  const status = runsResult.reason instanceof OperatorApiError ? runsResult.reason.status : 0
  return {
    context,
    runs: null,
    error: status === 404 ? "Trace not found" : "Trace metadata is unavailable. No mock values are substituted.",
  }
}

export async function LiveTracePage({
  traceId,
  searchParams,
}: Readonly<{
  traceId: string
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>
}>) {
  const resolved = searchParams instanceof Promise ? await searchParams : (searchParams ?? {})
  const returnHref = safeExploreReturnHref(resolved.return)
  const { context, runs, error } = await load(traceId)
  return (
    <DashboardShell liveMode operatorContext={context} showPreviewBanner={false}>
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <Link
            className="inline-flex min-h-6 items-center text-sm text-muted-foreground underline-offset-4 hover:underline"
            href={returnHref}
          >
            ← Back to Explore
          </Link>
          {error ? (
            <Card className={`${panelClass} mt-4`}>
              <CardContent className="py-10 text-center">
                <h1 className="text-lg font-medium">{error}</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  Unknown or out-of-tenant IDs do not reveal whether another trace exists.
                </p>
              </CardContent>
            </Card>
          ) : null}
          {runs ? (
            <Card className={`${panelClass} mt-4`}>
              <CardHeader>
                <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">
                  Trace runs · deterministic listing
                </p>
                <CardTitle className="mt-2 break-all font-mono text-xl">
                  <CopyId value={traceId} label="trace_id" />
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                  {runs.returned_count} run{runs.returned_count === 1 ? "" : "s"} · open a run for the metadata inspector
                </p>
              </CardHeader>
              <CardContent className="space-y-3">
                {runs.items.map((item) => (
                  <div key={item.run_id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <CopyId value={item.run_id} label="run_id" />
                      <Link
                        className="inline-flex min-h-6 items-center text-sm underline-offset-4 hover:underline"
                        href={`/dashboard/explore/r/${encodeURIComponent(item.run_id)}?return=${encodeURIComponent(returnHref)}`}
                      >
                        Open run
                      </Link>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {item.request_id} · {item.status} · {item.evidence.publication_state} ·{" "}
                      {item.evidence.completeness}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </main>
    </DashboardShell>
  )
}
