"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { IconCopy, IconDownload, IconLock, IconX } from "@tabler/icons-react"
import { toast } from "sonner"

import { EmptyState } from "@/components/list/empty-state"
import { StatusDot } from "@/components/list/status-dot"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { AuditEntry, CallerAuthz } from "@/lib/settings/types"
import { cn } from "@/lib/utils"

const ACTION_PREFIXES = [
  "all",
  "directive",
  "token",
  "memory",
  "org",
  "audit",
  "legal_hold",
] as const

function actionTone(
  action: string,
): "destructive" | "write" | "read" | "neutral" {
  const a = action.toLowerCase()
  if (
    a.includes("delete") ||
    a.includes("revoke") ||
    a.includes("suspend") ||
    a.includes("export") ||
    a.includes("hold")
  ) {
    return "destructive"
  }
  if (
    a.includes("create") ||
    a.includes("promote") ||
    a.includes("write") ||
    a.includes("update") ||
    a.includes("place")
  ) {
    return "write"
  }
  if (a.includes("read") || a.includes("list") || a.includes("get")) {
    return "read"
  }
  return "neutral"
}

function resourceHref(e: AuditEntry): string | null {
  if (!e.resource_linkable) return null
  switch (e.resource_type) {
    case "directive":
      return `/dashboard/directives/${e.resource_id}`
    case "memory":
      return `/dashboard/memories/${e.resource_id}`
    case "token":
      return `/dashboard/settings?tab=tokens`
    default:
      return null
  }
}

function canReadAudit(caller: CallerAuthz): boolean {
  // admin:audit_log bit dropped — gate on owner/admin until a dedicated bit lands.
  return caller.role === "owner" || caller.role === "admin"
}

function dualApprovalLabel(e: AuditEntry): string | null {
  if (!e.requires_second_actor) return null
  if (e.second_actor_user_id) {
    return `Second approval · ${e.second_actor_email ?? e.second_actor_user_id}`
  }
  return "Pending second approval"
}

export function AuditPanel({
  entries,
  caller,
  retentionDays,
  tier,
  onExportLogged,
}: {
  entries: AuditEntry[]
  caller: CallerAuthz
  retentionDays: number
  tier: string
  onExportLogged: (entry: AuditEntry) => void
}) {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()

  const actor = params.get("actor") ?? "all"
  const actionPrefix = params.get("action") ?? "all"
  const resource = params.get("resource") ?? "all"
  const outcome = params.get("outcome") ?? "all"
  const q = params.get("q") ?? ""
  const selectedId = params.get("entry")

  const setFilter = React.useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString())
      next.set("tab", "audit")
      if (!value || value === "all" || value === "") next.delete(key)
      else next.set(key, value)
      next.delete("entry")
      const qs = next.toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
    },
    [params, pathname, router],
  )

  const openEntry = (id: string) => {
    const next = new URLSearchParams(params.toString())
    next.set("tab", "audit")
    next.set("entry", id)
    router.replace(`${pathname}?${next.toString()}`, { scroll: false })
  }

  const closeEntry = () => {
    const next = new URLSearchParams(params.toString())
    next.delete("entry")
    const qs = next.toString()
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
  }

  if (!canReadAudit(caller)) {
    return (
      <Card className={panelClass}>
        <CardContent className="px-4 py-12">
          <EmptyState
            title="Audit log restricted"
            description="Owner or admin role required. A dedicated admin:audit_log permission bit was dropped and has no backing bit yet — do not expose full history to any authenticated user."
          />
        </CardContent>
      </Card>
    )
  }

  const actors = Array.from(new Set(entries.map((e) => e.actor))).sort((a, b) =>
    a.localeCompare(b),
  )
  const resources = Array.from(
    new Set(entries.map((e) => e.resource_type)),
  ).sort((a, b) => a.localeCompare(b))

  const filtered = entries
    .filter((e) => {
      if (actor !== "all" && e.actor !== actor) return false
      if (actionPrefix !== "all" && !e.action.startsWith(`${actionPrefix}.`)) {
        return false
      }
      if (resource !== "all" && e.resource_type !== resource) return false
      if (outcome === "success" && !e.success) return false
      if (outcome === "denied" && e.success) return false
      if (q.trim()) {
        const hay =
          `${e.actor} ${e.action} ${e.resource_id} ${e.error_code ?? ""}`.toLowerCase()
        if (!hay.includes(q.trim().toLowerCase())) return false
      }
      // Legal-hold detail: hide hold-specific rows without LegalHoldManage
      if (
        e.action.startsWith("legal_hold.") &&
        !caller.bits.includes("LegalHoldManage")
      ) {
        return false
      }
      return true
    })
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))

  const selected = filtered.find((e) => e.entry_id === selectedId) ?? null

  const exportFiltered = (format: "csv" | "json") => {
    const payload =
      format === "json" ? JSON.stringify(filtered, null, 2) : toCsv(filtered)
    void navigator.clipboard.writeText(payload)
    const logged: AuditEntry = {
      entry_id: `aud_export_${Date.now()}`,
      at: new Date().toISOString(),
      actor: "operator@example.invalid",
      actor_kind: "user",
      service_name: null,
      action: "audit.export",
      resource_type: "audit_log",
      resource_id: `export_${format}_${Date.now()}`,
      resource_linkable: false,
      ip: "203.0.113.10",
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      request_id: `req_export_${Date.now()}`,
      trace_id: null,
      success: true,
      error_code: null,
      error_message: null,
      data_classification: "confidential",
      previous_state: null,
      new_state: { format, rows: filtered.length },
      step_up_verified: false,
      step_up_jti: null,
      preview_token: null,
      idempotency_key: `idem_export_${Date.now()}`,
      requires_second_actor: false,
      second_actor_user_id: null,
      second_actor_email: null,
      second_actor_at: null,
    }
    onExportLogged(logged)
    toast.success(`Copied ${format.toUpperCase()} · audit.export logged`)
  }

  return (
    <>
      <Card className={panelClass}>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
          <div>
            <CardTitle className="text-[13px] font-medium">
              Audit & Actions
            </CardTitle>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              Unified audit_log + operator_action_ledger · append-only · hash
              chain (not Merkle/WORM) · history available: last {retentionDays}d
              ({tier})
            </p>
          </div>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              onClick={() => exportFiltered("csv")}
            >
              <IconDownload className="size-3.5" />
              Export CSV
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              onClick={() => exportFiltered("json")}
            >
              Export JSON
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3">
          <div className="flex flex-wrap gap-2">
            <Input
              value={q}
              onChange={(e) => setFilter("q", e.target.value)}
              placeholder="Search actor, action, resource…"
              className="h-8 max-w-xs text-[12px]"
            />
            <Select value={actor} onValueChange={(v) => setFilter("actor", v)}>
              <SelectTrigger className="h-8 w-[160px] text-[12px]">
                <SelectValue placeholder="Actor" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All actors</SelectItem>
                {actors.map((a) => (
                  <SelectItem key={a} value={a}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={actionPrefix}
              onValueChange={(v) => setFilter("action", v)}
            >
              <SelectTrigger className="h-8 w-[140px] text-[12px]">
                <SelectValue placeholder="Action" />
              </SelectTrigger>
              <SelectContent>
                {ACTION_PREFIXES.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p === "all" ? "All actions" : `${p}.*`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={resource}
              onValueChange={(v) => setFilter("resource", v)}
            >
              <SelectTrigger className="h-8 w-[140px] text-[12px]">
                <SelectValue placeholder="Resource" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All resources</SelectItem>
                {resources.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={outcome}
              onValueChange={(v) => setFilter("outcome", v)}
            >
              <SelectTrigger className="h-8 w-[130px] text-[12px]">
                <SelectValue placeholder="Outcome" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All outcomes</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="denied">Denied</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Filters are URL-serializable — share this view with a security
            reviewer. Read API for audit is fixture-backed until GET
            /v1/audit-log ships. Residual (#853): ClickHouse MergeTree TTL can
            still age rows under legal hold.
          </p>

          {filtered.length === 0 ? (
            <EmptyState
              title="No matching audit events"
              description="Widen filters or clear the search query."
            />
          ) : (
            <ul className="divide-y divide-border/50 rounded-lg border border-border/70">
              {filtered.map((e) => (
                <AuditRow
                  key={e.entry_id}
                  entry={e}
                  active={e.entry_id === selectedId}
                  onOpen={() => openEntry(e.entry_id)}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {selected ? (
        <AuditDetailDrawer entry={selected} onClose={closeEntry} />
      ) : null}
    </>
  )
}

function AuditRow({
  entry,
  active,
  onOpen,
}: {
  entry: AuditEntry
  active: boolean
  onOpen: () => void
}) {
  const href = resourceHref(entry)
  const dual = dualApprovalLabel(entry)
  const tone = actionTone(entry.action)

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className={cn(
          "flex w-full flex-col gap-1 px-3.5 py-3 text-left transition-colors hover:bg-muted/40",
          active && "bg-muted/50",
          !entry.success && "bg-destructive/[0.03]",
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              entry.success ? "bg-emerald-500" : "bg-destructive",
            )}
            aria-hidden
          />
          <span className="text-[13px] font-medium">
            {entry.actor_kind === "service"
              ? `system (${entry.service_name ?? "service"})`
              : entry.actor}
          </span>
          <ActionPill action={entry.action} tone={tone} />
          {href ? (
            <Link
              href={href}
              className="font-mono text-[11px] text-muted-foreground underline-offset-2 hover:underline"
              onClick={(ev) => ev.stopPropagation()}
            >
              {entry.resource_type}/{entry.resource_id}
            </Link>
          ) : (
            <span className="font-mono text-[11px] text-muted-foreground">
              {entry.resource_type}/{entry.resource_id}
            </span>
          )}
          {entry.data_classification === "restricted" ? (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground">
              <IconLock className="size-2.5" />
              restricted
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-3.5 text-[11px] text-muted-foreground">
          <span className="font-mono">
            {entry.at.replace("T", " ").slice(0, 19)}Z
          </span>
          <span>·</span>
          {entry.success ? (
            <StatusDot tone="ok" label="success" />
          ) : (
            <StatusDot
              tone="error"
              label={`DENIED${entry.error_code ? ` · ${entry.error_code}` : ""}`}
            />
          )}
          {entry.step_up_verified ? (
            <>
              <span>·</span>
              <span>step-up verified</span>
            </>
          ) : null}
          {dual ? (
            <>
              <span>·</span>
              <span
                className={cn(
                  !entry.second_actor_user_id &&
                    "text-amber-700 dark:text-amber-400",
                )}
              >
                {dual}
              </span>
            </>
          ) : null}
        </div>
        {!entry.success && entry.error_message ? (
          <p className="pl-3.5 text-[11px] text-muted-foreground">
            {entry.error_message}
          </p>
        ) : null}
        {(entry.preview_token || entry.idempotency_key) && (
          <p className="pl-3.5 font-mono text-[10px] text-muted-foreground/80">
            {entry.preview_token
              ? `preview_token: ${entry.preview_token.slice(0, 10)}…`
              : null}
            {entry.preview_token && entry.idempotency_key ? " · " : null}
            {entry.idempotency_key
              ? `idempotency: ${entry.idempotency_key.slice(0, 12)}…`
              : null}
          </p>
        )}
      </button>
    </li>
  )
}

function ActionPill({
  action,
  tone,
}: {
  action: string
  tone: ReturnType<typeof actionTone>
}) {
  return (
    <span
      className={cn(
        "rounded border px-1.5 py-0.5 font-mono text-[10px]",
        tone === "destructive" && "border-border bg-muted text-foreground",
        tone === "write" &&
          "border-amber-500/30 bg-amber-500/8 text-foreground",
        tone === "read" && "border-border/70 text-muted-foreground",
        tone === "neutral" && "border-border text-foreground",
      )}
    >
      {action}
    </span>
  )
}

function AuditDetailDrawer({
  entry,
  onClose,
}: {
  entry: AuditEntry
  onClose: () => void
}) {
  const [raw, setRaw] = React.useState(false)
  const href = resourceHref(entry)

  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-background/50 backdrop-blur-[2px]">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close drawer"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal
        aria-labelledby="audit-detail-title"
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border bg-card shadow-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
          <div>
            <h2 id="audit-detail-title" className="text-[14px] font-medium">
              {entry.action}
            </h2>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
              {entry.entry_id}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="size-7 p-0"
            onClick={onClose}
          >
            <IconX className="size-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 text-[12px]">
          <section className="space-y-1.5">
            <Meta label="Actor">
              {entry.actor_kind === "service"
                ? `system (${entry.service_name})`
                : entry.actor}{" "}
              <span className="text-muted-foreground">
                · {entry.actor_kind}
              </span>
            </Meta>
            <Meta label="When">
              <span className="font-mono">
                {entry.at.replace("T", " ").slice(0, 19)}Z
              </span>
            </Meta>
            <Meta label="Outcome">
              {entry.success ? (
                <StatusDot tone="ok" label="success" />
              ) : (
                <StatusDot tone="error" label={entry.error_code ?? "DENIED"} />
              )}
            </Meta>
            <Meta label="Resource">
              {href ? (
                <Link href={href} className="font-mono hover:underline">
                  {entry.resource_type}/{entry.resource_id}
                </Link>
              ) : (
                <span className="font-mono text-muted-foreground">
                  {entry.resource_type}/{entry.resource_id}
                </span>
              )}
            </Meta>
            <Meta label="Classification">
              <span className="inline-flex items-center gap-1">
                {entry.data_classification === "restricted" ? (
                  <IconLock className="size-3" />
                ) : null}
                {entry.data_classification}
              </span>
            </Meta>
          </section>

          {(entry.requires_second_actor ||
            entry.preview_token ||
            entry.step_up_verified) && (
            <section className="space-y-2 rounded-md border border-border/70 px-3 py-2.5">
              <div className="text-[11px] font-medium text-muted-foreground">
                Operator ledger
              </div>
              {entry.step_up_verified ? (
                <p>
                  Step-up verified
                  {entry.step_up_jti ? (
                    <span className="ml-1 font-mono text-[10px] text-muted-foreground">
                      {entry.step_up_jti}
                    </span>
                  ) : null}
                </p>
              ) : null}
              {entry.requires_second_actor ? (
                <p>
                  {entry.second_actor_user_id ? (
                    <>
                      Second actor{" "}
                      <span className="font-medium">
                        {entry.second_actor_email}
                      </span>{" "}
                      at{" "}
                      <span className="font-mono text-[11px]">
                        {entry.second_actor_at?.replace("T", " ").slice(0, 19)}Z
                      </span>
                    </>
                  ) : (
                    <span className="text-amber-700 dark:text-amber-400">
                      Pending second approval — distinct from loading
                    </span>
                  )}
                </p>
              ) : null}
              {entry.preview_token ? (
                <CopyLine label="preview_token" value={entry.preview_token} />
              ) : null}
              {entry.idempotency_key ? (
                <CopyLine
                  label="idempotency_key"
                  value={entry.idempotency_key}
                />
              ) : null}
            </section>
          )}

          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-medium text-muted-foreground">
                Before / after
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px]"
                onClick={() => setRaw((r) => !r)}
              >
                {raw ? "Structured" : "View raw JSON"}
              </Button>
            </div>
            {raw ? (
              <div className="grid gap-2">
                <pre className="overflow-auto rounded-md border border-border bg-muted/30 p-2 font-mono text-[10px]">
                  {JSON.stringify(entry.previous_state, null, 2)}
                </pre>
                <pre className="overflow-auto rounded-md border border-border bg-muted/30 p-2 font-mono text-[10px]">
                  {JSON.stringify(entry.new_state, null, 2)}
                </pre>
              </div>
            ) : (
              <StructuredDiff
                before={entry.previous_state}
                after={entry.new_state}
              />
            )}
          </section>

          <section className="space-y-1.5 rounded-md border border-border/70 px-3 py-2.5">
            <div className="text-[11px] font-medium text-muted-foreground">
              Request context
            </div>
            <Meta label="IP">
              <span className="font-mono">{entry.ip}</span>
            </Meta>
            {entry.user_agent ? (
              <Meta label="UA">
                <span className="line-clamp-2 text-[11px] text-muted-foreground">
                  {entry.user_agent}
                </span>
              </Meta>
            ) : null}
            {entry.request_id ? (
              <Meta label="request_id">
                <span className="font-mono text-[11px]">
                  {entry.request_id}
                </span>
              </Meta>
            ) : null}
            {entry.trace_id ? (
              <Meta label="trace_id">
                <Link
                  href={`/dashboard/explore/t/${entry.trace_id}`}
                  className="font-mono text-[11px] hover:underline"
                >
                  {entry.trace_id}
                </Link>
              </Meta>
            ) : null}
          </section>

          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Integrity: append-only hash chain. Not Merkle / WORM — do not imply
            stronger tamper-proof guarantees.
          </p>
        </div>
      </aside>
    </div>
  )
}

function Meta({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-2">
      <span className="w-24 shrink-0 text-[11px] text-muted-foreground">
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

function CopyLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate">{value}</span>
      <Button
        size="sm"
        variant="ghost"
        className="size-6 shrink-0 p-0"
        onClick={async () => {
          await navigator.clipboard.writeText(value)
          toast.success("Copied")
        }}
      >
        <IconCopy className="size-3" />
      </Button>
    </div>
  )
}

function StructuredDiff({
  before,
  after,
}: {
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}) {
  if (!before && !after) {
    return (
      <p className="text-[12px] text-muted-foreground">
        No state delta recorded.
      </p>
    )
  }
  const keys = Array.from(
    new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]),
  ).sort()

  return (
    <div className="overflow-hidden rounded-md border border-border/70">
      <table className="w-full text-left text-[11px]">
        <thead>
          <tr className="border-b border-border/60 bg-muted/30 text-muted-foreground">
            <th className="px-2.5 py-1.5 font-medium">Field</th>
            <th className="px-2.5 py-1.5 font-medium">Before</th>
            <th className="px-2.5 py-1.5 font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const b = before?.[k]
            const a = after?.[k]
            const changed = JSON.stringify(b) !== JSON.stringify(a)
            return (
              <tr
                key={k}
                className={cn(
                  "border-b border-border/40 last:border-0",
                  changed && "bg-amber-500/[0.06]",
                )}
              >
                <td className="px-2.5 py-1.5 font-mono">{k}</td>
                <td className="px-2.5 py-1.5 font-mono text-muted-foreground">
                  {fmt(b)}
                </td>
                <td className="px-2.5 py-1.5 font-mono">{fmt(a)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function fmt(v: unknown): string {
  if (v == null) return "—"
  if (
    typeof v === "string" ||
    typeof v === "number" ||
    typeof v === "boolean"
  ) {
    return String(v)
  }
  return JSON.stringify(v)
}

function toCsv(rows: AuditEntry[]): string {
  const headers = [
    "at",
    "actor",
    "action",
    "resource_type",
    "resource_id",
    "success",
    "error_code",
    "data_classification",
  ]
  const lines = [
    headers.join(","),
    ...rows.map((r) =>
      [
        r.at,
        r.actor,
        r.action,
        r.resource_type,
        r.resource_id,
        r.success,
        r.error_code ?? "",
        r.data_classification,
      ]
        .map((c) => `"${String(c).replace(/"/g, '""')}"`)
        .join(","),
    ),
  ]
  return lines.join("\n")
}

/** Settings tab from URL (`?tab=audit`); preserves other audit query keys. */
export function useAuditTabSync(defaultTab = "org") {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const tab = params.get("tab") ?? defaultTab

  const setTab = React.useCallback(
    (next: string) => {
      const sp = new URLSearchParams(params.toString())
      if (next === defaultTab) sp.delete("tab")
      else sp.set("tab", next)
      if (next !== "audit") {
        sp.delete("entry")
        sp.delete("actor")
        sp.delete("action")
        sp.delete("resource")
        sp.delete("outcome")
        sp.delete("q")
      }
      const qs = sp.toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
    },
    [defaultTab, params, pathname, router],
  )

  return { tab, setTab }
}
