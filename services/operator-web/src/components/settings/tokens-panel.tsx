"use client"

import * as React from "react"
import { IconCopy, IconDots, IconLock, IconX } from "@tabler/icons-react"
import { toast } from "sonner"

import { EmptyState, EmptyStateButton } from "@/components/list/empty-state"
import { StatusDot } from "@/components/list/status-dot"
import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { AGENT_STORE } from "@/lib/agents/fixtures"
import {
  SettingsApiError,
  createPatToken,
  revokePatToken,
  tokenStatus,
} from "@/lib/settings/api"
import { evaluateGate, gateMessage } from "@/lib/settings/fixtures"
import type { PatToken, SettingsPageV2 } from "@/lib/settings/types"
import { cn } from "@/lib/utils"

const CALLER_USER_ID = "usr_devon"

type ExpirePreset = "never" | "30d" | "90d" | "custom"

export function TokensPanel({
  data,
  onChange,
  requireStepUp,
}: {
  data: SettingsPageV2
  onChange: (tokens: PatToken[]) => void
  requireStepUp: (action: () => void) => void
}) {
  const onboarding = useOnboardingOptional()
  const [createOpen, setCreateOpen] = React.useState(false)
  const [reveal, setReveal] = React.useState<string | null>(null)

  const canCreate = !evaluateGate(data.caller, { bit: "TokenCreate" })

  const openCreate = () => {
    const block = evaluateGate(data.caller, { bit: "TokenCreate" })
    if (block) {
      toast.error(gateMessage(block))
      return
    }
    setCreateOpen(true)
  }

  const onRevoke = async (t: PatToken) => {
    try {
      const next = await revokePatToken(t, {
        caller: data.caller,
        callerUserId: CALLER_USER_ID,
      })
      onChange(data.tokens.map((x) => (x.token_id === t.token_id ? next : x)))
      toast.success("Token revoked")
    } catch (e) {
      if (e instanceof SettingsApiError && e.status === 404) {
        toast.error("Token not found")
        return
      }
      toast.error(e instanceof Error ? e.message : "Revoke failed")
    }
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div>
          <CardTitle className="text-[13px] font-medium">API Tokens</CardTitle>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            GET/POST /v1/tokens · plaintext once · elevation denied for bits you
            don&apos;t hold
          </p>
        </div>
        <Button
          size="sm"
          className="h-8 shrink-0"
          disabled={!canCreate}
          onClick={openCreate}
        >
          + Create Token
        </Button>
      </CardHeader>
      <CardContent className="px-0 py-0">
        {data.tokens.length === 0 ? (
          <EmptyState
            title="No API tokens yet"
            description="Create a Personal Access Token for SDK and CI access. Ties into onboarding step 2."
            action={
              <EmptyStateButton
                onClick={() => {
                  openCreate()
                  onboarding?.setActiveStep("issue_pat")
                }}
              >
                Create your first token
              </EmptyStateButton>
            }
          />
        ) : (
          <TokenTable
            tokens={data.tokens}
            callerBits={data.caller.bits}
            onRevoke={onRevoke}
          />
        )}
      </CardContent>

      {createOpen ? (
        <CreateTokenModal
          data={data}
          onClose={() => setCreateOpen(false)}
          requireStepUp={requireStepUp}
          onCreated={(token, plaintext) => {
            onChange([token, ...data.tokens])
            setCreateOpen(false)
            setReveal(plaintext)
            onboarding?.setProgress((p) => ({
              ...p,
              pat_token_id: token.token_id,
              pat_prefix: token.prefix,
              pat_scopes: token.permissions,
              pat_plaintext: plaintext,
            }))
          }}
        />
      ) : null}

      {reveal ? (
        <TokenRevealPanel
          plaintext={reveal}
          onDone={() => {
            setReveal(null)
            onboarding?.setProgress((p) => ({ ...p, pat_plaintext: null }))
          }}
        />
      ) : null}
    </Card>
  )
}

function TokenTable({
  tokens,
  callerBits,
  onRevoke,
}: {
  tokens: PatToken[]
  callerBits: string[]
  onRevoke: (t: PatToken) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[12px]">
        <thead>
          <tr className="border-b border-border/60 text-[11px] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Name</th>
            <th className="px-4 py-2.5 font-medium">Prefix</th>
            <th className="px-4 py-2.5 font-medium">Permissions</th>
            <th className="px-4 py-2.5 font-medium">Created</th>
            <th className="px-4 py-2.5 font-medium">Expires</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium" />
          </tr>
        </thead>
        <tbody>
          {tokens.map((t) => {
            const status = tokenStatus(t)
            const isOwn = t.owner_user_id === CALLER_USER_ID
            const canRevoke =
              !t.is_revoked && (isOwn || callerBits.includes("TokenRevoke"))
            return (
              <tr
                key={t.token_id}
                className="border-b border-border/40 last:border-0"
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-foreground">{t.name}</div>
                  {t.agent_id ? (
                    <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      {t.agent_id}
                    </div>
                  ) : null}
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                  {t.prefix}…
                </td>
                <td className="px-4 py-3">
                  <PermChips perms={t.permissions} />
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                  {t.created_at.slice(0, 10)}
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                  {t.expires_at ? t.expires_at.slice(0, 10) : "Never"}
                </td>
                <td className="px-4 py-3">
                  <StatusDot
                    tone={
                      status === "active"
                        ? "ok"
                        : status === "expired"
                          ? "warn"
                          : "muted"
                    }
                    label={
                      status === "active"
                        ? "Active"
                        : status === "expired"
                          ? "Expired"
                          : "Revoked"
                    }
                  />
                </td>
                <td className="px-4 py-3 text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="size-7 p-0"
                        aria-label="Token actions"
                      >
                        <IconDots className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        disabled={!canRevoke}
                        onSelect={() => onRevoke(t)}
                      >
                        Revoke
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function PermChips({ perms }: { perms: string[] }) {
  const shown = perms.slice(0, 2)
  const rest = perms.length - shown.length
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {shown.map((p) => (
        <span
          key={p}
          className="rounded border border-border/70 bg-muted/40 px-1.5 py-0.5 font-mono text-[10px]"
        >
          {p}
        </span>
      ))}
      {rest > 0 ? (
        <span
          className="rounded border border-border/70 px-1.5 py-0.5 text-[10px] text-muted-foreground"
          title={perms.slice(2).join(", ")}
        >
          +{rest} more
        </span>
      ) : null}
    </span>
  )
}

function CreateTokenModal({
  data,
  onClose,
  onCreated,
  requireStepUp,
}: {
  data: SettingsPageV2
  onClose: () => void
  onCreated: (token: PatToken, plaintext: string) => void
  requireStepUp: (action: () => void) => void
}) {
  const [name, setName] = React.useState("")
  const [perms, setPerms] = React.useState<string[]>(["trace:read"])
  const [expire, setExpire] = React.useState<ExpirePreset>("never")
  const [customDate, setCustomDate] = React.useState("")
  const [agentId, setAgentId] = React.useState<string>("none")
  const [busy, setBusy] = React.useState(false)

  const groups = [
    "Memory",
    "Directive",
    "Session",
    "Trace",
    "Admin",
    "Federation",
  ] as const

  const expiresAt = (): string | null => {
    if (expire === "never") return null
    if (expire === "custom") {
      return customDate ? new Date(customDate).toISOString() : null
    }
    const days = expire === "30d" ? 30 : 90
    return new Date(Date.now() + days * 86_400_000).toISOString()
  }

  const submit = () => {
    const needsMfa = perms.some(
      (w) => data.permission_picker.find((p) => p.wire === w)?.requires_mfa,
    )
    const run = async () => {
      setBusy(true)
      try {
        const res = await createPatToken(
          {
            name,
            permissions: perms,
            expires_at: expiresAt(),
            agent_id: agentId === "none" ? null : agentId,
          },
          {
            caller: data.caller,
            picker: data.permission_picker,
            ownerUserId: CALLER_USER_ID,
          },
        )
        onCreated(res.token, res.plaintext)
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Create failed")
      } finally {
        setBusy(false)
      }
    }
    if (needsMfa) requireStepUp(() => void run())
    else void run()
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="create-token-title"
        className="w-full max-w-lg rounded-2xl border border-border/80 bg-card shadow-[0_24px_80px_-28px_oklch(0_0_0_/_0.45)]"
      >
        <div className="flex items-center justify-between border-b border-border/60 px-5 py-3.5">
          <h2 id="create-token-title" className="text-[15px] font-medium">
            Create API Token
          </h2>
          <Button
            size="sm"
            variant="ghost"
            className="size-7 p-0"
            onClick={onClose}
            aria-label="Close"
          >
            <IconX className="size-4" />
          </Button>
        </div>
        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4">
          <label className="block space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              Name
            </span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9"
              placeholder="Production SDK"
              autoFocus
            />
          </label>

          <div>
            <div className="mb-2 text-[11px] font-medium text-muted-foreground">
              Permissions
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {groups.map((g) => (
                <div
                  key={g}
                  className="rounded-md border border-border/70 px-2.5 py-2"
                >
                  <div className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                    {g}
                  </div>
                  {data.permission_picker
                    .filter((p) => p.group === g)
                    .map((p) => {
                      const holds = data.caller.bits.includes(p.name)
                      return (
                        <label
                          key={p.wire}
                          className={cn(
                            "mt-1.5 flex items-center gap-2 text-[11px]",
                            !holds && "opacity-45",
                          )}
                          title={
                            !holds
                              ? "You don't hold this bit — elevation would 403"
                              : undefined
                          }
                        >
                          <Checkbox
                            checked={perms.includes(p.wire)}
                            disabled={!holds}
                            onCheckedChange={() => {
                              if (!holds) return
                              setPerms((prev) =>
                                prev.includes(p.wire)
                                  ? prev.filter((x) => x !== p.wire)
                                  : [...prev, p.wire],
                              )
                            }}
                          />
                          <span className="font-mono">{p.wire}</span>
                          {p.requires_mfa ? (
                            <IconLock className="size-2.5 text-muted-foreground" />
                          ) : null}
                        </label>
                      )
                    })}
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">
              Expires
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["never", "Never"],
                  ["30d", "30 days"],
                  ["90d", "90 days"],
                  ["custom", "Custom"],
                ] as const
              ).map(([k, label]) => (
                <Button
                  key={k}
                  type="button"
                  size="sm"
                  variant={expire === k ? "default" : "outline"}
                  className="h-7 text-[11px]"
                  onClick={() => setExpire(k)}
                >
                  {label}
                </Button>
              ))}
            </div>
            {expire === "custom" ? (
              <Input
                type="date"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
                className="mt-2 h-9 w-48"
              />
            ) : null}
          </div>

          <label className="block space-y-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              Agent scope (optional)
            </span>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="All agents" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">All agents</SelectItem>
                {AGENT_STORE.slice(0, 8).map((a) => (
                  <SelectItem key={a.agent_id} value={a.agent_id}>
                    {a.name} · {a.slug}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <p className="text-[11px] leading-relaxed text-muted-foreground">
            IP allowlisting (`allowed_ips`) is syntax-validated only today — not
            persisted or enforced. Omitted here until enforcement lands.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-border/60 px-5 py-3">
          <Button size="sm" variant="ghost" className="h-8" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            className="h-8"
            disabled={busy || !name.trim() || perms.length === 0}
            onClick={submit}
          >
            {busy ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  )
}

function TokenRevealPanel({
  plaintext,
  onDone,
}: {
  plaintext: string
  onDone: () => void
}) {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-background/85 p-4 backdrop-blur-md">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="reveal-token-title"
        className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl"
      >
        <h2
          id="reveal-token-title"
          className="text-[18px] font-medium tracking-tight"
        >
          Copy your token now
        </h2>
        <p className="mt-2 rounded-xl border border-amber-500/35 bg-amber-500/8 px-3.5 py-2.5 text-[12px] leading-relaxed">
          This is shown only once. You will not be able to view it again.
        </p>
        <code className="mt-4 block break-all rounded-xl border border-border/70 bg-muted/40 px-3.5 py-3 font-mono text-[12px] leading-relaxed">
          {plaintext}
        </code>
        <div className="mt-4 flex gap-2">
          <Button
            className="h-9 flex-1"
            onClick={async () => {
              await navigator.clipboard.writeText(plaintext)
              toast.success("Copied to clipboard")
            }}
          >
            <IconCopy className="size-3.5" />
            Copy token
          </Button>
          <Button variant="outline" className="h-9" onClick={onDone}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}
