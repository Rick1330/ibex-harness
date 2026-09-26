"use client"

import * as React from "react"
import { IconDots } from "@tabler/icons-react"
import { toast } from "sonner"

import { EmptyState, EmptyStateButton } from "@/components/list/empty-state"
import { StatusDot } from "@/components/list/status-dot"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SettingsApiError,
  revokePatToken,
  tokenStatus,
} from "@/lib/settings/api"
import type { PatToken, SettingsPageV2 } from "@/lib/settings/types"

const CALLER_USER_ID = "operator-preview"

export function TokensPanel({
  data,
  onChange,
}: {
  data: SettingsPageV2
  onChange: (tokens: PatToken[]) => void
}) {
  const openCreate = () => {
    toast.info("AuthService integration is required before creating tokens.")
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
            Token metadata is read-only until AuthService is connected · elevation denied for bits you
            don&apos;t hold
          </p>
        </div>
      </CardHeader>
      <CardContent className="px-0 py-0">
        {data.tokens.length === 0 ? (
          <EmptyState
            title="No API tokens yet"
            description="Token creation is disabled until AuthService is connected."
            action={
              <EmptyStateButton
                onClick={openCreate}
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
