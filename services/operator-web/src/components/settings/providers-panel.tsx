"use client"

import * as React from "react"
import { IconX } from "@tabler/icons-react"
import { toast } from "sonner"

import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  SettingsApiError,
  relativeValidated,
  removeProviderCredential,
  upsertProviderCredential,
} from "@/lib/settings/api"
import {
  PROVIDER_CATALOG,
  evaluateGate,
  gateMessage,
} from "@/lib/settings/fixtures"
import type { ProviderCredential, SettingsPageV2 } from "@/lib/settings/types"
import { cn } from "@/lib/utils"

export function ProvidersPanel({
  data,
  onChange,
}: {
  data: SettingsPageV2
  onChange: (providers: ProviderCredential[]) => void
}) {
  const [modal, setModal] = React.useState<{
    mode: "connect" | "rotate"
    providerName: string
    existing?: ProviderCredential
  } | null>(null)

  const byName = new Map(
    data.providers.map((p) => [p.provider_name.toLowerCase(), p]),
  )

  const openConnect = (providerName: string) => {
    const block = evaluateGate(data.caller, { bit: "OrgSettingsWrite" })
    if (block) {
      toast.error(gateMessage(block))
      return
    }
    const existing = byName.get(providerName.toLowerCase())
    setModal({
      mode: existing ? "rotate" : "connect",
      providerName,
      existing,
    })
  }

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
        <Button
          size="sm"
          className="h-8"
          onClick={() => {
            const block = evaluateGate(data.caller, { bit: "OrgSettingsWrite" })
            if (block) {
              toast.error(gateMessage(block))
              return
            }
            setModal({ mode: "connect", providerName: "openai" })
          }}
        >
          + Add Provider
        </Button>
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
                      variant="outline"
                      className="h-7 text-[11px]"
                      onClick={() => openConnect(cat.id)}
                    >
                      Rotate
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-[11px]"
                      onClick={() => void onRemove(cred)}
                    >
                      Remove
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    className="h-7 text-[11px]"
                    onClick={() => openConnect(cat.id)}
                  >
                    + Connect
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </CardContent>

      {modal ? (
        <ProviderKeyModal
          mode={modal.mode}
          providerName={modal.providerName}
          existing={modal.existing}
          caller={data.caller}
          onClose={() => setModal(null)}
          onSaved={(cred) => {
            const rest = data.providers.filter(
              (p) =>
                p.provider_name.toLowerCase() !==
                cred.provider_name.toLowerCase(),
            )
            onChange([cred, ...rest])
            setModal(null)
            toast.success(
              cred.status === "active"
                ? "Validated and sealed — plaintext cleared"
                : "Upstream validation failed — status: invalid",
            )
          }}
        />
      ) : null}
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

function ProviderKeyModal({
  mode,
  providerName,
  existing,
  caller,
  onClose,
  onSaved,
}: {
  mode: "connect" | "rotate"
  providerName: string
  existing?: ProviderCredential
  caller: SettingsPageV2["caller"]
  onClose: () => void
  onSaved: (c: ProviderCredential) => void
}) {
  const [key, setKey] = React.useState("")
  const [baseUrl, setBaseUrl] = React.useState(existing?.base_url ?? "")
  const [busy, setBusy] = React.useState(false)
  const label =
    PROVIDER_CATALOG.find((p) => p.id === providerName)?.label ?? providerName

  const submit = async () => {
    setBusy(true)
    try {
      const cred = await upsertProviderCredential(
        {
          provider_name: providerName,
          api_key: key,
          base_url: baseUrl.trim() || null,
        },
        { caller, existing },
      )
      onSaved(cred)
    } catch (e) {
      if (e instanceof SettingsApiError) toast.error(e.message)
      else toast.error("Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal
        className="w-full max-w-md rounded-2xl border border-border/80 bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border/60 px-5 py-3.5">
          <h2 className="text-[15px] font-medium">
            {mode === "rotate" ? "Rotate" : "Connect"} {label}
          </h2>
          <Button
            size="sm"
            variant="ghost"
            className="size-7 p-0"
            onClick={onClose}
          >
            <IconX className="size-4" />
          </Button>
        </div>
        <div className="space-y-3 px-5 py-4">
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            {mode === "rotate"
              ? "Submit a new key. The previous secret is never shown or retrievable — only key_hint (last 4) remains."
              : "Write-once plaintext. After upstream validation the key is sealed; only key_hint is stored."}
          </p>
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">API key</span>
            <Input
              type="password"
              autoComplete="off"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="h-9 font-mono text-[12px]"
              placeholder="sk-…"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Base URL (optional)
            </span>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="h-9 font-mono text-[12px]"
              placeholder="https://api.openai.com/v1"
            />
          </label>
          <p className="text-[10px] text-muted-foreground">
            Demo: keys starting with <span className="font-mono">bad</span> fail
            validation → status invalid.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-border/60 px-5 py-3">
          <Button size="sm" variant="ghost" className="h-8" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            className="h-8"
            disabled={busy || key.trim().length < 8}
            onClick={() => void submit()}
          >
            {busy ? "Validating…" : mode === "rotate" ? "Rotate key" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  )
}
