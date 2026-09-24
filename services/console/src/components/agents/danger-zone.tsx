"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AgentApiError, archiveAgent, deleteAgent } from "@/lib/agents/api"
import type { AgentDetail } from "@/lib/agents/types"

export function AgentDangerZone({
  agent,
  onArchived,
}: {
  agent: AgentDetail
  onArchived: (next: AgentDetail) => void
}) {
  const router = useRouter()
  const [busy, setBusy] = React.useState<"archive" | "delete" | null>(null)
  const canDelete = agent.total_sessions === 0

  const archive = async () => {
    setBusy("archive")
    try {
      const next = await archiveAgent(agent.agent_id)
      onArchived(next)
      toast.success("Agent archived", {
        description: "Reversible via Activate from archived state.",
      })
    } catch (e) {
      toast.error(e instanceof AgentApiError ? e.message : "Archive failed")
    } finally {
      setBusy(null)
    }
  }

  const remove = async () => {
    if (!canDelete) return
    setBusy("delete")
    try {
      await deleteAgent(agent.agent_id)
      toast.success("Agent deleted")
      router.push("/dashboard/agents")
    } catch (e) {
      if (e instanceof AgentApiError) {
        toast.error(`${e.code}: ${e.message}`)
      } else {
        toast.error("Delete failed")
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card className={`${panelClass} border-destructive/30`}>
      <CardHeader className="gap-1 border-b border-destructive/20 bg-destructive/5 px-4 py-3">
        <CardTitle className="text-[13px] font-medium text-destructive">
          Danger zone
        </CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Archive and Delete are separate controls — backends differ (204 vs 409
          AGENT_HAS_SESSIONS).
        </p>
      </CardHeader>
      <CardContent className="space-y-4 px-4 py-4 text-[13px]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-medium">Archive agent</div>
            <p className="text-[12px] text-muted-foreground">
              Soft lifecycle end. Existing history retained; can be reactivated.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null || agent.status === "archived"}
            onClick={archive}
          >
            {busy === "archive" ? "Archiving…" : "Archive"}
          </Button>
        </div>

        <div className="flex flex-wrap items-start justify-between gap-3 border-t pt-4">
          <div>
            <div className="font-medium">Delete agent</div>
            {canDelete ? (
              <p className="text-[12px] text-muted-foreground">
                Soft-delete. Allowed because total_sessions = 0.
              </p>
            ) : (
              <p className="text-[12px] text-destructive">
                Blocked: agent has {agent.total_sessions.toLocaleString()}{" "}
                sessions (409 AGENT_HAS_SESSIONS). Archive instead.
              </p>
            )}
          </div>
          <Button
            size="sm"
            variant="destructive"
            disabled={!canDelete || busy !== null}
            title={
              canDelete
                ? "Permanently soft-delete this agent"
                : "Delete blocked while sessions exist"
            }
            onClick={remove}
          >
            {busy === "delete" ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
