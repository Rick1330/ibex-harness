"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import { DashboardShell, pagePad } from "@/components/sessions/dashboard-shell"
import { TraceInspector } from "@/components/trace-inspector/trace-inspector"
import { Button } from "@/components/ui/button"
import { TRACE_BY_ID } from "@/lib/explore/fixtures"

export default function TraceInspectorPage() {
  const params = useParams<{ traceId: string }>()
  const traceId = params.traceId
  const trace = TRACE_BY_ID[traceId]

  return (
    <DashboardShell>
      {trace ? (
        <TraceInspector trace={trace} />
      ) : (
        <div className={`${pagePad} items-center gap-3 py-16 text-center`}>
          <h1 className="text-lg font-medium">Trace not found</h1>
          <p className="mx-auto max-w-md text-sm text-muted-foreground">
            Cross-tenant guarantee: unknown or out-of-org{" "}
            <span className="font-mono">{traceId}</span> returns 404 / empty —
            never a &quot;found but forbidden&quot; signal.
          </p>
          <Button asChild size="sm">
            <Link href="/dashboard/explore">Back to Explore</Link>
          </Button>
        </div>
      )}
    </DashboardShell>
  )
}
