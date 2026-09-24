"use client"

import { IconInfoCircle } from "@tabler/icons-react"

import { StatusDot } from "@/components/list/status-dot"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { SettingsPageV2 } from "@/lib/settings/types"

export function WebhooksPanel({
  data,
}: {
  data: SettingsPageV2
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div>
          <CardTitle className="text-[13px] font-medium">Webhooks</CardTitle>
          <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[12px] text-muted-foreground">
            POST /v1/webhooks · HMAC signing (SECURITY.md §9)
            <SigningTooltip />
          </p>
        </div>
        <span className="text-[11px] text-muted-foreground">
          Secure integration deferred
        </span>
      </CardHeader>
      <CardContent className="space-y-3 px-4 py-3">
        {data.webhooks.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-muted-foreground">
            No webhook endpoints yet.
          </p>
        ) : (
          data.webhooks.map((w) => (
            <div
              key={w.webhook_id}
              className="rounded-lg border border-border/70 px-3.5 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-mono text-[12px]">{w.url}</div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <StatusDot
                      tone={w.status === "active" ? "ok" : "muted"}
                      label={w.status === "active" ? "Active" : "Disabled"}
                    />
                    <span className="text-[11px] text-muted-foreground">
                      {w.events.length} event
                      {w.events.length === 1 ? "" : "s"} subscribed
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {w.secret_set
                        ? "Signing secret set ✓"
                        : "No signing secret"}
                    </span>
                  </div>
                </div>

              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {w.events.map((e) => (
                  <span
                    key={e}
                    className="rounded border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                  >
                    {e}
                  </span>
                ))}
              </div>
              <div className="mt-3 rounded-md border border-dashed border-border/70 px-2.5 py-2 text-[11px] text-muted-foreground">
                Recent deliveries — coming soon. No delivery-log endpoint in the
                reviewed API yet; history is not fabricated.
              </div>
            </div>
          ))
        )}
      </CardContent>

    </Card>
  )
}

function SigningTooltip() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex text-muted-foreground hover:text-foreground"
          aria-label="Signing contract"
        >
          <IconInfoCircle className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-[11px] leading-relaxed">
        Outbound: X-IBEX-Signature: sha256=&#123;hmac&#125; + X-IBEX-Timestamp.
        Verify with ±5min replay window; every payload carries event_id for
        dedup (SECURITY.md §9).
      </TooltipContent>
    </Tooltip>
  )
}
