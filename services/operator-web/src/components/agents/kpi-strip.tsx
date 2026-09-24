"use client"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { formatCompact, formatTokens, relativeTime } from "@/lib/agents/api"
import type { AgentDetail } from "@/lib/agents/types"
import { panelClass } from "@/components/sessions/dashboard-shell"

export function AgentKpiStrip({ agent }: { agent: AgentDetail }) {
  const items = [
    {
      label: "Total sessions",
      value: formatCompact(agent.total_sessions),
      hint: "lifetime",
    },
    {
      label: "Total memories",
      value: formatCompact(agent.total_memories),
      hint: "extracted",
    },
    {
      label: "Tokens used",
      value: formatTokens(agent.total_tokens_used),
      hint: "lifetime",
    },
    {
      label: "Last active",
      value: relativeTime(agent.last_active_at),
      hint: agent.last_active_at
        ? new Date(agent.last_active_at).toLocaleString()
        : "no traffic yet",
    },
  ]

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label} className={panelClass}>
          <CardHeader className="gap-1 px-4 py-3">
            <CardDescription className="text-[11px] tracking-wide uppercase">
              {item.label}
            </CardDescription>
            <CardTitle
              className="font-serif text-2xl font-normal tabular-nums tracking-tight"
              title={item.hint}
            >
              {item.value}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 text-[11px] text-muted-foreground">
            {item.hint}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
