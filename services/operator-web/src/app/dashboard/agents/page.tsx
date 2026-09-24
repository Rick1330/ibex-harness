"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { AgentStatusBadge } from "@/components/agents/status-badge"
import { CreateAgentForm } from "@/components/agents/create-agent-form"
import { CopyId } from "@/components/explore/copy-id"
import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { listTable } from "@/components/explore/table-styles"
import {
  FilterBar,
  ListPageHeader,
  type FilterPill,
} from "@/components/list/filter-bar"
import { EnvPill } from "@/components/list/status-dot"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"
import { DashboardShell, pagePad } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
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
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AgentApiError,
  activateAgent,
  formatCompact,
  formatTokens,
  listAgents,
  pauseAgent,
  relativeTime,
} from "@/lib/agents/api"
import { ALL_TAGS } from "@/lib/agents/fixtures"
import type { AgentListItem, AgentStatus } from "@/lib/agents/types"
import { cn } from "@/lib/utils"
import { IconDots } from "@tabler/icons-react"

type ViewState = "loading" | "empty" | "error" | "success"

const STATUSES: AgentStatus[] = ["active", "paused", "suspended", "archived"]

function AgentsWorkbench() {
  const router = useRouter()
  const onboarding = useOnboardingOptional()
  const orgId = onboarding?.orgId ?? "org_acme"
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState("")
  const [status, setStatus] = React.useState<AgentStatus | "all">("all")
  const [tags, setTags] = React.useState<string[]>([])
  const [rows, setRows] = React.useState<AgentListItem[]>([])
  const [total, setTotal] = React.useState(0)
  const [error, setError] = React.useState<string | null>(null)
  const [creating, setCreating] = React.useState(false)

  const load = React.useCallback(async () => {
    setView("loading")
    setError(null)
    try {
      if (onboarding?.demoZeroAgents) {
        setRows([])
        setTotal(0)
        setView("empty")
        return
      }
      const res = await listAgents({
        status,
        tags,
        search: q,
        limit: 100,
      })
      setRows(res.items)
      setTotal(res.total_count)
      setView(res.total_count === 0 ? "empty" : "success")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed")
      setView("error")
    }
  }, [status, tags, q, onboarding?.demoZeroAgents])

  React.useEffect(() => {
    void load()
  }, [load])

  const pager = usePagination(rows, 15, "accumulate")

  const openCreate = () => {
    setCreating(true)
    onboarding?.setActiveStep("create_agent")
  }

  const pills: FilterPill[] = []
  if (status !== "all") {
    pills.push({
      id: "status",
      label: `Status ${status}`,
      onRemove: () => setStatus("all"),
    })
  }
  for (const t of tags) {
    pills.push({
      id: `tag-${t}`,
      label: `Tag ${t}`,
      onRemove: () => setTags((prev) => prev.filter((x) => x !== t)),
    })
  }
  if (q.trim()) {
    pills.push({
      id: "q",
      label: `Search ${q.trim()}`,
      onRemove: () => setQ(""),
    })
  }

  const toggleTag = (t: string) => {
    setTags((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    )
  }

  const onPause = async (id: string) => {
    try {
      const res = await pauseAgent(id)
      toast.message("Agent paused", { description: res.message })
      await load()
    } catch (e) {
      toast.error(e instanceof AgentApiError ? e.message : "Pause failed")
    }
  }

  const onActivate = async (id: string) => {
    try {
      await activateAgent(id)
      toast.success("Agent activated")
      await load()
    } catch (e) {
      toast.error(e instanceof AgentApiError ? e.message : "Activate failed")
    }
  }

  return (
    <div className={pagePad}>
      <ListPageHeader
        title="Agents"
        description="Lifecycle, config, and routing — wired to /v1/agents"
        actions={
          <Button size="sm" onClick={openCreate}>
            + New Agent
          </Button>
        }
      />

      <FilterBar
        pills={pills}
        onAddFilter={() =>
          toast.message("Add Filter", {
            description: "Use status, tags, or search on the right.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name / description…"
              className="h-8 w-48 text-[12px] md:w-56"
              aria-label="Search agents"
            />
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as AgentStatus | "all")}
            >
              <SelectTrigger
                size="sm"
                className="w-[130px]"
                aria-label="Status"
              >
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">all</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline" className="h-8 text-[12px]">
                  Tags{tags.length ? ` (${tags.length})` : ""}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {ALL_TAGS.map((t) => (
                  <DropdownMenuItem
                    key={t}
                    onSelect={(e) => {
                      e.preventDefault()
                      toggleTag(t)
                    }}
                  >
                    <span className={tags.includes(t) ? "font-medium" : ""}>
                      {tags.includes(t) ? "✓ " : ""}
                      {t}
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      {creating ? (
        <CreateAgentForm
          orgId={orgId}
          onCancel={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false)
            onboarding?.setDemoZeroAgents(false)
            void load()
            router.push(`/dashboard/agents/${id}`)
          }}
        />
      ) : null}

      {view === "loading" && (
        <div className="space-y-0 pt-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-none border-b" />
          ))}
        </div>
      )}

      {view === "error" && (
        <div className="px-1 py-12 text-center text-[13px]">
          Couldn&apos;t load agents
          {error ? (
            <span className="mt-1 block font-mono text-[12px] text-muted-foreground">
              {error}
            </span>
          ) : null}
          <div className="mt-3">
            <Button size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        </div>
      )}

      {view === "empty" && !creating && (
        <PageEmptyState
          page="agents"
          actionLabel="+ New Agent"
          onAction={openCreate}
        />
      )}

      {view === "success" && rows.length === 0 && (
        <div className="px-1 py-10 text-center text-[13px] text-muted-foreground">
          No agents match these filters.
        </div>
      )}

      {view === "success" && rows.length > 0 && (
        <AgentsTable
          rows={pager.slice}
          pager={pager}
          total={total}
          onOpen={(id) => router.push(`/dashboard/agents/${id}`)}
          onPause={onPause}
          onActivate={onActivate}
          onRefresh={() => void load()}
        />
      )}
    </div>
  )
}

function AgentsTable({
  rows,
  pager,
  total,
  onOpen,
  onPause,
  onActivate,
  onRefresh,
}: {
  rows: AgentListItem[]
  pager: ReturnType<typeof usePagination<AgentListItem>>
  total: number
  onOpen: (id: string) => void
  onPause: (id: string) => Promise<void>
  onActivate: (id: string) => Promise<void>
  onRefresh: () => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Usage</TableHead>
            <TableHead className={listTable.head}>Directive</TableHead>
            <TableHead className={listTable.head}>Provider</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Last active
            </TableHead>
            <TableHead className={listTable.head}>
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((a) => (
            <TableRow
              key={a.agent_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(a.agent_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[280px]")}>
                <div className={listTable.primary}>{a.name}</div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <CopyId
                    value={a.slug}
                    label="slug"
                    className="text-[11px] text-muted-foreground"
                  />
                </div>
                {a.description ? (
                  <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                    {a.description}
                  </div>
                ) : null}
              </TableCell>
              <TableCell className={listTable.cell}>
                <AgentStatusBadge status={a.status} />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                <div>{formatCompact(a.total_sessions)} sessions</div>
                <div className={listTable.meta}>
                  {formatCompact(a.total_memories)} mem ·{" "}
                  {formatTokens(a.total_tokens_used)}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                {a.active_directive_version != null ? (
                  <Link
                    href={`/dashboard/directives?q=${encodeURIComponent(a.slug)}`}
                    className="hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <EnvPill>
                      v{a.active_directive_version}
                      {a.active_directive_hash
                        ? ` · ${a.active_directive_hash}`
                        : ""}
                    </EnvPill>
                  </Link>
                ) : (
                  <span className="text-[12px] text-muted-foreground">
                    none
                  </span>
                )}
              </TableCell>
              <TableCell className={listTable.cell}>
                {a.default_provider && a.default_model ? (
                  <EnvPill>
                    {a.default_provider} · {a.default_model}
                  </EnvPill>
                ) : (
                  <span className="text-[12px] text-muted-foreground">
                    platform default
                  </span>
                )}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
                title={a.last_active_at ?? undefined}
              >
                {relativeTime(a.last_active_at)}
              </TableCell>
              <TableCell
                className={listTable.cell}
                onClick={(e) => e.stopPropagation()}
              >
                <RowActions
                  agent={a}
                  onPause={onPause}
                  onActivate={onActivate}
                  onRefresh={onRefresh}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="px-1 pt-2 text-[11px] text-muted-foreground tabular-nums">
        Showing {pager.from}–{pager.to} of {total}
      </p>
      <PaginationBar
        page={pager.page}
        pageCount={pager.pageCount}
        total={pager.total}
        from={pager.from}
        to={pager.to}
        onPageChange={pager.setPage}
        label="agents"
        variant="load-more"
      />
    </div>
  )
}

function RowActions({
  agent,
  onPause,
  onActivate,
  onRefresh,
}: {
  agent: AgentListItem
  onPause: (id: string) => Promise<void>
  onActivate: (id: string) => Promise<void>
  onRefresh: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="icon-xs" variant="ghost" aria-label="Agent actions">
          <IconDots className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {agent.status === "active" && (
          <DropdownMenuItem
            onSelect={() => {
              void onPause(agent.agent_id)
            }}
          >
            Pause
          </DropdownMenuItem>
        )}
        {(agent.status === "paused" ||
          agent.status === "suspended" ||
          agent.status === "archived") && (
          <DropdownMenuItem
            onSelect={() => {
              void onActivate(agent.agent_id)
            }}
          >
            Activate
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onSelect={async () => {
            const { archiveAgent } = await import("@/lib/agents/api")
            try {
              await archiveAgent(agent.agent_id)
              toast.success("Agent archived")
              onRefresh()
            } catch (e) {
              toast.error(
                e instanceof AgentApiError ? e.message : "Archive failed",
              )
            }
          }}
        >
          Archive
        </DropdownMenuItem>
        <DropdownMenuItem disabled>
          Delete — open detail danger zone
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default function AgentsPage() {
  return (
    <DashboardShell>
      <AgentsWorkbench />
    </DashboardShell>
  )
}
