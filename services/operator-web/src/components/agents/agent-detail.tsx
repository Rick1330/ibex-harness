"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { AgentConfigForm } from "@/components/agents/config-form"
import { AgentDangerZone } from "@/components/agents/danger-zone"
import { AgentKpiStrip } from "@/components/agents/kpi-strip"
import { AgentStatusBadge } from "@/components/agents/status-badge"
import { CopyId } from "@/components/explore/copy-id"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  AgentApiError,
  activateAgent,
  pauseAgent,
  patchAgent,
  relativeTime,
} from "@/lib/agents/api"
import type { AgentDetail } from "@/lib/agents/types"

export function AgentDetailView({ initial }: { initial: AgentDetail }) {
  const [agent, setAgent] = React.useState(initial)
  const [name, setName] = React.useState(initial.name)
  const [busy, setBusy] = React.useState(false)

  React.useEffect(() => {
    setAgent(initial)
    setName(initial.name)
  }, [initial])

  const saveName = async () => {
    if (name.trim() === agent.name) return
    try {
      const next = await patchAgent(agent.agent_id, { name: name.trim() })
      setAgent(next)
      toast.success("Name updated")
    } catch (e) {
      setName(agent.name)
      toast.error(
        e instanceof AgentApiError
          ? `${e.code}: ${e.message}`
          : "Name update failed",
      )
    }
  }

  const pause = async () => {
    setBusy(true)
    try {
      const res = await pauseAgent(agent.agent_id)
      setAgent(res.agent)
      toast.message("Agent paused", { description: res.message })
    } catch (e) {
      toast.error(e instanceof AgentApiError ? e.message : "Pause failed")
    } finally {
      setBusy(false)
    }
  }

  const activate = async () => {
    setBusy(true)
    try {
      const next = await activateAgent(agent.agent_id)
      setAgent(next)
      toast.success("Agent activated")
    } catch (e) {
      toast.error(e instanceof AgentApiError ? e.message : "Activate failed")
    } finally {
      setBusy(false)
    }
  }

  const sessionsHref = `/dashboard/sessions?q=${encodeURIComponent(agent.name)}`
  const tracesHref = `/dashboard/explore?q=agent:${encodeURIComponent(agent.slug)}`
  const memoriesHref = `/dashboard/memories?q=${encodeURIComponent(agent.slug)}`
  const directiveHref = agent.active_directive_version
    ? `/dashboard/directives?q=${encodeURIComponent(agent.slug)}`
    : "/dashboard/directives"

  return (
    <div className="space-y-3">
      <Card className={panelClass}>
        <CardHeader className="gap-3 border-b px-4 py-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-2">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={saveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur()
                }}
                className="h-9 max-w-md border-transparent bg-transparent px-0 text-[16px] font-medium shadow-none focus-visible:border-input focus-visible:bg-background"
                aria-label="Agent name"
              />
              <div className="flex flex-wrap items-center gap-2">
                <CopyId
                  value={agent.slug}
                  label="slug"
                  className="text-[12px] text-muted-foreground"
                />
                <span
                  className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground"
                  title="Slug is immutable after creation — used in external integrations and routing keys."
                >
                  immutable
                </span>
                <AgentStatusBadge status={agent.status} />
              </div>
              {agent.description && (
                <p className="text-[13px] text-muted-foreground">
                  {agent.description}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {agent.status !== "active" && agent.status !== "archived" && (
                <Button size="sm" disabled={busy} onClick={activate}>
                  Activate
                </Button>
              )}
              {agent.status === "archived" && (
                <Button size="sm" disabled={busy} onClick={activate}>
                  Reactivate
                </Button>
              )}
              {agent.status === "active" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={pause}
                >
                  Pause
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
      </Card>

      <AgentKpiStrip agent={agent} />

      <Card className={panelClass}>
        <CardHeader className="gap-1 border-b px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Active directive
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-3 text-[13px]">
          {agent.active_directive_version != null ? (
            <div className="flex flex-wrap items-center gap-2">
              <Link href={directiveHref} className="font-mono hover:underline">
                v{agent.active_directive_version}
                {agent.active_directive_hash
                  ? ` · ${agent.active_directive_hash}`
                  : ""}
              </Link>
              <Button asChild size="sm" variant="outline">
                <Link href={directiveHref}>Open in Directives →</Link>
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">
                No directive assigned yet
              </span>
              <Button asChild size="sm">
                <Link href="/dashboard/directives">Assign directive</Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <AgentConfigForm agent={agent} onSaved={setAgent} />

      <Tabs defaultValue="sessions">
        <TabsList variant="line">
          <TabsTrigger value="sessions" className="text-[13px]">
            Sessions
          </TabsTrigger>
          <TabsTrigger value="traces" className="text-[13px]">
            Traces
          </TabsTrigger>
          <TabsTrigger value="memories" className="text-[13px]">
            Memories
          </TabsTrigger>
          <TabsTrigger value="analytics" className="text-[13px]">
            Analytics
          </TabsTrigger>
        </TabsList>
        <TabsContent value="sessions" className="mt-3">
          <CrossLinkCard
            title="Sessions for this agent"
            body="Opens Sessions pre-filtered — does not duplicate the 4.D.3 surface."
            href={sessionsHref}
            cta="Open Sessions →"
          />
        </TabsContent>
        <TabsContent value="traces" className="mt-3">
          <CrossLinkCard
            title="Traces for this agent"
            body="Opens Explore with agent-scoped query chips preserved in the URL."
            href={tracesHref}
            cta="Open Explore →"
          />
        </TabsContent>
        <TabsContent value="memories" className="mt-3">
          <CrossLinkCard
            title="Memories for this agent"
            body="Opens Memories scoped by agent slug search."
            href={memoriesHref}
            cta="Open Memories →"
          />
        </TabsContent>
        <TabsContent value="analytics" className="mt-3">
          <Card className={panelClass}>
            <CardContent className="px-4 py-10 text-center">
              <div className="text-[13px] font-medium">
                Agent-level analytics not yet available
              </div>
              <p className="mx-auto mt-1 max-w-md text-[12px] text-muted-foreground">
                <span className="font-mono">GET /v1/agents/{"{id}"}/stats</span>{" "}
                is explicitly deferred / out of scope in milestone 4.A.3. Use
                org-wide Analytics when that page ships — no fabricated charts
                here.
              </p>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Last active {relativeTime(agent.last_active_at)}
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <AgentDangerZone agent={agent} onArchived={setAgent} />
    </div>
  )
}

function CrossLinkCard({
  title,
  body,
  href,
  cta,
}: {
  title: string
  body: string
  href: string
  cta: string
}) {
  return (
    <Card className={panelClass}>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div>
          <div className="text-[13px] font-medium">{title}</div>
          <p className="text-[12px] text-muted-foreground">{body}</p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href={href}>{cta}</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
