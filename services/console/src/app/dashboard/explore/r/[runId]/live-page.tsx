import Link from "next/link"
import { cookies } from "next/headers"

import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent } from "@/components/ui/card"
import { fetchOperatorContext, fetchOperatorTraceResource } from "@/lib/api/d1"
import type { OperatorContext, OperatorTraceDetail } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"

import { RunInspector } from "./run-inspector"

function safeReturnHref(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (!value || !value.startsWith("/dashboard/explore")) return "/dashboard/explore"
  if (value.includes("//") || value.includes("\\")) return "/dashboard/explore"
  return value
}

async function load(
  runId: string,
): Promise<{ context: OperatorContext | null; trace: OperatorTraceDetail | null; error: string | null }> {
  const store = await cookies()
  const name = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = store.get(name)?.value
  const cookie = value ? `${name}=${value}` : undefined
  const [contextResult, traceResult] = await Promise.allSettled([
    fetchOperatorContext(cookie),
    fetchOperatorTraceResource("detail", cookie, runId),
  ])
  const context = contextResult.status === "fulfilled" ? contextResult.value : null
  if (traceResult.status === "fulfilled") {
    return { context, trace: traceResult.value, error: null }
  }
  const status = traceResult.reason instanceof OperatorApiError ? traceResult.reason.status : 0
  return {
    context,
    trace: null,
    error: status === 404 ? "Trace not found" : "Trace metadata is unavailable. No mock values are substituted.",
  }
}

export async function LiveRunPage({
  runId,
  searchParams,
}: Readonly<{
  runId: string
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>
}>) {
  const resolved = searchParams instanceof Promise ? await searchParams : (searchParams ?? {})
  const returnHref = safeReturnHref(resolved.return)
  const { context, trace, error } = await load(runId)
  return (
    <DashboardShell liveMode operatorContext={context} showPreviewBanner={false}>
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <Link className="text-sm text-muted-foreground underline-offset-4 hover:underline" href={returnHref}>
            ← Back to Explore
          </Link>
          <div className="sr-only" aria-live="polite">
            {error ?? (trace ? `Loaded run ${trace.run_id}` : "Loading run")}
          </div>
          {error ? (
            <Card className={`${panelClass} mt-4`}>
              <CardContent className="py-10 text-center">
                <h1 className="text-lg font-medium">{error}</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  Unknown or out-of-tenant IDs do not reveal whether another run exists.
                </p>
              </CardContent>
            </Card>
          ) : null}
          {trace ? <RunInspector trace={trace} /> : null}
        </div>
      </main>
    </DashboardShell>
  )
}
