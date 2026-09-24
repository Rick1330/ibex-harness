"use client"

import * as React from "react"
import { IconCopy, IconInfoCircle, IconX } from "@tabler/icons-react"
import { toast } from "sonner"

import { StatusDot } from "@/components/list/status-dot"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  SettingsApiError,
  createWebhookEndpoint,
  rotateWebhookSecret,
} from "@/lib/settings/api"
import {
  WEBHOOK_EVENTS,
  evaluateGate,
  gateMessage,
} from "@/lib/settings/fixtures"
import type { SettingsPageV2, WebhookEndpoint } from "@/lib/settings/types"

export function WebhooksPanel({
  data,
  onChange,
}: {
  data: SettingsPageV2
  onChange: (webhooks: WebhookEndpoint[]) => void
}) {
  const [createOpen, setCreateOpen] = React.useState(false)
  const [secretReveal, setSecretReveal] = React.useState<string | null>(null)

  const openCreate = () => {
    const block = evaluateGate(data.caller, { bit: "TokenCreate" })
    if (block) {
      toast.error(gateMessage(block))
      return
    }
    setCreateOpen(true)
  }

  const onRotate = async (w: WebhookEndpoint) => {
    try {
      const res = await rotateWebhookSecret(w, { caller: data.caller })
      onChange(
        data.webhooks.map((x) =>
          x.webhook_id === w.webhook_id ? res.webhook : x,
        ),
      )
      setSecretReveal(res.secret)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rotate failed")
    }
  }

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
        <Button size="sm" className="h-8 shrink-0" onClick={openCreate}>
          + Add Endpoint
        </Button>
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
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-[11px]"
                  onClick={() => void onRotate(w)}
                >
                  Rotate secret
                </Button>
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

      {createOpen ? (
        <CreateWebhookModal
          caller={data.caller}
          onClose={() => setCreateOpen(false)}
          onCreated={(webhook, secret) => {
            onChange([webhook, ...data.webhooks])
            setCreateOpen(false)
            setSecretReveal(secret)
          }}
        />
      ) : null}

      {secretReveal ? (
        <SecretRevealPanel
          title="Copy signing secret now"
          secret={secretReveal}
          hint="Receivers verify X-IBEX-Signature (sha256 HMAC) + X-IBEX-Timestamp (±5min) and dedupe on event_id."
          onDone={() => setSecretReveal(null)}
        />
      ) : null}
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

function CreateWebhookModal({
  caller,
  onClose,
  onCreated,
}: {
  caller: SettingsPageV2["caller"]
  onClose: () => void
  onCreated: (w: WebhookEndpoint, secret: string) => void
}) {
  const [url, setUrl] = React.useState("")
  const [events, setEvents] = React.useState<string[]>([
    "memory.conflict_detected",
    "drift.detected",
  ])
  const [busy, setBusy] = React.useState(false)

  const toggle = (e: string) => {
    setEvents((prev) =>
      prev.includes(e) ? prev.filter((x) => x !== e) : [...prev, e],
    )
  }

  const submit = async () => {
    setBusy(true)
    try {
      const res = await createWebhookEndpoint({ url, events }, { caller })
      onCreated(res.webhook, res.secret)
    } catch (e) {
      if (e instanceof SettingsApiError) toast.error(e.message)
      else toast.error("Create failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal
        className="w-full max-w-lg rounded-2xl border border-border/80 bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border/60 px-5 py-3.5">
          <h2 className="text-[15px] font-medium">Add webhook endpoint</h2>
          <Button
            size="sm"
            variant="ghost"
            className="size-7 p-0"
            onClick={onClose}
          >
            <IconX className="size-4" />
          </Button>
        </div>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4">
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">HTTPS URL</span>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="h-9 font-mono text-[12px]"
              placeholder="https://your-server.com/ibex-webhooks"
            />
          </label>
          <div>
            <div className="mb-2 text-[11px] font-medium text-muted-foreground">
              Events (by domain)
            </div>
            <div className="space-y-3">
              {WEBHOOK_EVENTS.map((g) => (
                <div
                  key={g.domain}
                  className="rounded-md border border-border/70 px-2.5 py-2"
                >
                  <div className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                    {g.domain}
                  </div>
                  {g.events.map((ev) => (
                    <label
                      key={ev}
                      className="mt-1.5 flex items-center gap-2 text-[11px]"
                    >
                      <Checkbox
                        checked={events.includes(ev)}
                        onCheckedChange={() => toggle(ev)}
                      />
                      <span className="font-mono">{ev}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Signing secret is generated on create and shown once — same pattern
            as PATs. Permission: TokenCreate (bit 36).
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-border/60 px-5 py-3">
          <Button size="sm" variant="ghost" className="h-8" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            className="h-8"
            disabled={busy || !url.trim() || events.length === 0}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  )
}

function SecretRevealPanel({
  title,
  secret,
  hint,
  onDone,
}: {
  title: string
  secret: string
  hint: string
  onDone: () => void
}) {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-background/85 p-4 backdrop-blur-md">
      <div
        role="dialog"
        aria-modal
        className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl"
      >
        <h2 className="text-[18px] font-medium tracking-tight">{title}</h2>
        <p className="mt-2 rounded-xl border border-amber-500/35 bg-amber-500/8 px-3.5 py-2.5 text-[12px] leading-relaxed">
          Shown only once. You will not be able to view it again.
        </p>
        <code className="mt-4 block break-all rounded-xl border border-border/70 bg-muted/40 px-3.5 py-3 font-mono text-[12px]">
          {secret}
        </code>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          {hint}
        </p>
        <div className="mt-4 flex gap-2">
          <Button
            className="h-9 flex-1"
            onClick={async () => {
              await navigator.clipboard.writeText(secret)
              toast.success("Copied")
            }}
          >
            <IconCopy className="size-3.5" />
            Copy secret
          </Button>
          <Button variant="outline" className="h-9" onClick={onDone}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}
