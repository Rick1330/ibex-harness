"use client"

import * as React from "react"
import Link from "next/link"
import { useParams } from "next/navigation"

import { AgentDetailView } from "@/components/agents/agent-detail"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { AgentApiError, getAgent } from "@/lib/agents/api"
import type { AgentDetail } from "@/lib/agents/types"

export default function AgentDetailPage() {
  const params = useParams<{ agentId: string }>()
  const [agent, setAgent] = React.useState<AgentDetail | null>(null)
  const [state, setState] = React.useState<"loading" | "ready" | "not_found">(
    "loading",
  )

  React.useEffect(() => {
    let cancelled = false
    setState("loading")
    void getAgent(params.agentId)
      .then((a) => {
        if (cancelled) return
        setAgent(a)
        setState("ready")
      })
      .catch((e) => {
        if (cancelled) return
        // Identical UI for missing vs cross-tenant (API 404 for both).
        if (e instanceof AgentApiError && e.status === 404) {
          setState("not_found")
        } else {
          setState("not_found")
        }
      })
    return () => {
      cancelled = true
    }
  }, [params.agentId])

  return (
    <DashboardShell>
      <div className={pagePad}>
        <Button asChild size="sm" variant="ghost" className="-ml-2 mb-1">
          <Link href="/dashboard/agents">← Agents</Link>
        </Button>

        {state === "loading" && (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-64 w-full rounded-lg" />
          </div>
        )}

        {state === "not_found" && (
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">Agent not found</div>
              <p className="mt-1 text-[12px] text-muted-foreground">
                No agent matches{" "}
                <span className="font-mono">{params.agentId}</span> in this org.
              </p>
              <Button asChild size="sm" className="mt-3">
                <Link href="/dashboard/agents">Back to Agents</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {state === "ready" && agent && <AgentDetailView initial={agent} />}
      </div>
    </DashboardShell>
  )
}
