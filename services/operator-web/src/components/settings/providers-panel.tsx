"use client"

import * as React from "react"
import { toast } from "sonner"

import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { relativeValidated, removeProviderCredential } from "@/lib/settings/api"
import { PROVIDER_CATALOG } from "@/lib/settings/fixtures"
import type { ProviderCredential, SettingsPageV2 } from "@/lib/settings/types"
import { cn } from "@/lib/utils"

export function ProvidersPanel({
  data,
  onChange,
}: {
  data: SettingsPageV2
  onChange: (providers: ProviderCredential[]) => void
}) {
  const byName = new Map(
    data.providers.map((p) => [p.provider_name.toLowerCase(), p]),
  )

  const onRemove = async (p: ProviderCredential) => {
    try {
      await removeProviderCredential(p.provider_id, { caller: data.caller })
      onChange(data.providers.filter((x) => x.provider_id !== p.provider_id))
      toast.success("Provider removed")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Remove failed")
    }
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div>
          <CardTitle className="text-[13px] font-medium">
            Provider Credentials
          </CardTitle>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            GET/POST /v1/organizations/{"{org_id}"}/providers · metadata only —
            keys sealed after write
          </p>
        </div>
        <span className="text-[11px] text-muted-foreground">
          Secure integration deferred
        </span>
      </CardHeader>
      <CardContent className="divide-y divide-border/50 px-0 py-0">
        {PROVIDER_CATALOG.map((cat) => {
          const cred = byName.get(cat.id)
          return (
            <div
              key={cat.id}
              className="flex flex-wrap items-center gap-3 px-4 py-3.5"
            >
              <ProviderStatus cred={cred} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium">{cat.label}</div>
                {cred ? (
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    key: {cred.key_hint}
                    {cred.base_url ? ` · ${cred.base_url}` : ""}
                    {" · "}
                    {relativeValidated(cred.last_validated_at)}
                  </p>
                ) : (
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    not configured
                  </p>
                )}
              </div>
              <div className="flex gap-1.5">
                {cred ? (
                  <>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-[11px]"
                      onClick={() => void onRemove(cred)}
                    >
                      Remove
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
          )
        })}
      </CardContent>

    </Card>
  )
}

function ProviderStatus({ cred }: { cred?: ProviderCredential }) {
  const tone = !cred
    ? "bg-muted-foreground/40"
    : cred.status === "active"
      ? "bg-emerald-500"
      : cred.status === "invalid"
        ? "bg-red-500"
        : "bg-amber-500"
  return (
    <span
      aria-label={
        !cred
          ? "not configured"
          : cred.status === "active"
            ? "active"
            : cred.status === "invalid"
              ? "validation failed"
              : "rotating"
      }
      className={cn("size-2 shrink-0 rounded-full", tone)}
    />
  )
}
