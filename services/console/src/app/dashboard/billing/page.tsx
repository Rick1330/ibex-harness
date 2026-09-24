"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"

import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"
import { TierQuotaCard } from "@/components/org/tier-quota-card"
import {
  ChartLegendSwatch,
  MetricTrend,
} from "@/components/charts/metric-trend"
import { listTable } from "@/components/explore/table-styles"
import { ListPageHeader } from "@/components/list/filter-bar"
import { StatusDot } from "@/components/list/status-dot"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  BILLING_V2,
  centsUsd,
  matchModelPattern,
  projectExhaustion,
} from "@/lib/billing/fixtures"
import type {
  BudgetPeriod,
  EnforcementDecision,
  RateCard,
  UsageQueryShape,
} from "@/lib/billing/types"
import { cn } from "@/lib/utils"

const usd = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(n)

const full = new Intl.NumberFormat("en-US")

const SHAPES: { id: UsageQueryShape; label: string }[] = [
  { id: "org_time_aggregate", label: "Org / time" },
  { id: "agent_session_breakdown", label: "Agent / session" },
  { id: "request_point_lookup", label: "Request" },
  { id: "fallback_attribution", label: "Fallback" },
  { id: "tool_correlation", label: "Tool" },
]

function BillingWorkbench() {
  const onboarding = useOnboardingOptional()
  const data = BILLING_V2
  const [budget, setBudget] = React.useState(data.budgets[0]!)
  const [hardCapConfirm, setHardCapConfirm] = React.useState(false)
  const [selectedCard, setSelectedCard] = React.useState(data.rate_cards[0]!)
  const [versionId, setVersionId] = React.useState(
    selectedCard.versions[0]!.version_id,
  )
  const [showDryRun, setShowDryRun] = React.useState(false)
  const [shape, setShape] =
    React.useState<UsageQueryShape>("org_time_aggregate")
  const [modelProbe, setModelProbe] = React.useState("claude-3-opus")

  const version =
    selectedCard.versions.find((v) => v.version_id === versionId) ??
    selectedCard.versions[0]!
  const matched = matchModelPattern(modelProbe, version.prices)
  const exhaustion = projectExhaustion(
    budget.spent_cents_cached,
    budget.cap_cents,
    budget.daily_spend_cents,
  )
  const usage = data.usage_by_shape[shape]
  const remaining = Math.max(0, budget.cap_cents - budget.spent_cents_cached)
  const pct = Math.min(
    100,
    (budget.spent_cents_cached / budget.cap_cents) * 100,
  )
  const isEmpty = onboarding?.demoZeroAgents || onboarding?.agentCount === 0

  React.useEffect(() => {
    onboarding?.setProgress((p) =>
      p.budget_visited || p.budget_skipped ? p : { ...p, budget_visited: true },
    )
    // Mark budget step visited once when landing on Billing.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-shot
  }, [])

  if (isEmpty) {
    return (
      <div className={pagePad}>
        <ListPageHeader
          title="Billing"
          description="Estimated spend, budgets, and rate cards"
        />
        <PageEmptyState page="billing" actionLabel="Open setup / set budget" />
      </div>
    )
  }

  return (
    <div className={pagePad}>
      {/* Header actions — page name lives in the site breadcrumb */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="sr-only">Billing</h1>
          <p className="text-[13px] text-muted-foreground">
            Estimated spend for this org · invoice actuals deferred (#859)
          </p>
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          <span className="rounded-md border border-border px-2 py-1 font-mono text-[11px]">
            {data.org.tier}
          </span>
          <PeriodPicker
            budgets={data.budgets}
            selected={budget}
            onSelect={(b) => {
              setBudget(b)
              setHardCapConfirm(false)
            }}
          />
        </div>
      </div>

      {/* Spend hero — single column, full width chart */}
      <section id="budgets" className="rise mt-6 space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[12px] text-muted-foreground">
              {budget.period_start.slice(0, 10)} →{" "}
              {budget.period_end.slice(0, 10)}
            </p>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="text-[42px] leading-none font-medium tracking-tight tabular-nums md:text-[48px]">
                {usd(centsUsd(budget.spent_cents_cached))}
              </span>
              <span className="text-[15px] text-muted-foreground">
                / {usd(centsUsd(budget.cap_cents))}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-6 text-[13px]">
            <Stat label="Remaining" value={usd(centsUsd(remaining))} />
            <Stat label="Used" value={`${pct.toFixed(0)}%`} />
            <Stat
              label="Mode"
              value={
                budget.enforcement_mode === "hard_cap"
                  ? "Hard cap"
                  : "Alert only"
              }
            />
            {exhaustion ? <Stat label="Exhausts" value={exhaustion} /> : null}
          </div>
        </div>

        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500",
              pct >= 100
                ? "bg-destructive"
                : pct >= 80
                  ? "bg-amber-600 dark:bg-amber-500"
                  : "bg-foreground",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>

        <MetricTrend
          title="Cumulative spend (cached rollup)"
          data={budget.daily_spend_cents.map((d) => ({
            t: d.day.slice(5),
            value: centsUsd(d.cumulative_cents),
          }))}
          dataKey="value"
          referenceY={centsUsd(budget.cap_cents)}
          referenceYLabel="cap"
          height={200}
          yFormatter={(v) => `$${Math.round(v)}`}
          marks={
            budget.daily_spend_cents.length
              ? [
                  {
                    x: budget.daily_spend_cents[
                      budget.daily_spend_cents.length - 1
                    ]!.day.slice(5),
                    y: centsUsd(budget.spent_cents_cached),
                    tone: pct >= 80 ? "amber" : "foreground",
                  },
                ]
              : undefined
          }
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-4">
            <ChartLegendSwatch
              className="border-dashed border-muted-foreground"
              label="Cap"
            />
            <ChartLegendSwatch
              className="bg-foreground"
              label="Spend (not real-time)"
            />
          </div>
          <EnforcementControls
            mode={budget.enforcement_mode}
            hardCapConfirm={hardCapConfirm}
            setHardCapConfirm={setHardCapConfirm}
            onHardCap={() => {
              setBudget((b) => ({ ...b, enforcement_mode: "hard_cap" }))
              setHardCapConfirm(false)
              toast.success("Switched to hard cap")
            }}
            onAlertOnly={() => {
              setBudget((b) => ({ ...b, enforcement_mode: "alert_only" }))
              toast.message("Switched to alert only")
            }}
          />
        </div>

        {budget.enforcement_mode === "hard_cap" ? (
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            Hard cap blocks overspend with{" "}
            <span className="font-mono text-foreground">
              402 BUDGET_EXCEEDED
            </span>{" "}
            on chat completions.
          </p>
        ) : (
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            Alert only — traffic can exceed the cap. Enable a hard cap before
            production if you need a hard stop.
          </p>
        )}
      </section>

      {/* Everything else behind tabs — no stacked wall */}
      <Tabs defaultValue="plan" className="rise mt-8">
        <TabsList className="mb-4 h-auto flex-wrap">
          <TabsTrigger value="plan">Plan</TabsTrigger>
          <TabsTrigger value="rates">Rates</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="decisions">Decisions</TabsTrigger>
        </TabsList>

        <TabsContent value="plan" className="mt-0">
          <TierQuotaCard org={data.org} showComparison={false} />
        </TabsContent>

        <TabsContent value="rates" className="mt-0 space-y-4">
          <RateCardsSection
            data={data}
            selectedCard={selectedCard}
            setSelectedCard={(c) => {
              setSelectedCard(c)
              setVersionId(c.versions[0]!.version_id)
              setShowDryRun(false)
            }}
            versionId={versionId}
            setVersionId={setVersionId}
            version={version}
            modelProbe={modelProbe}
            setModelProbe={setModelProbe}
            matched={matched}
            showDryRun={showDryRun}
            setShowDryRun={setShowDryRun}
          />
        </TabsContent>

        <TabsContent value="usage" className="mt-0 space-y-3">
          <p className="text-[12px] text-muted-foreground">
            Five query shapes only. All costs estimated.
          </p>
          <Tabs
            value={shape}
            onValueChange={(v) => setShape(v as UsageQueryShape)}
          >
            <TabsList className="h-auto flex-wrap">
              {SHAPES.map((s) => (
                <TabsTrigger key={s.id} value={s.id} className="text-[11px]">
                  {s.label}
                </TabsTrigger>
              ))}
            </TabsList>
            <TabsContent value={shape} className="mt-3 space-y-2">
              {usage.completeness !== "complete" || usage.truncated ? (
                <div className="rounded-md border border-border/70 bg-muted/30 px-3 py-2 text-[12px] text-muted-foreground">
                  {usage.completeness !== "complete"
                    ? "Partial data — some ClickHouse buckets incomplete"
                    : null}
                  {usage.truncated
                    ? `${usage.completeness !== "complete" ? " · " : ""}Truncated — not the full answer`
                    : null}
                </div>
              ) : null}
              <p className="text-[12px] text-muted-foreground">
                Showing{" "}
                <span className="font-mono text-foreground">
                  {full.format(usage.returned_count)}
                </span>{" "}
                of{" "}
                <span className="font-mono text-foreground">
                  {full.format(usage.matched_count)}
                </span>
              </p>
              <UsageShapeTable rows={usage.rows} />
            </TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="decisions" className="mt-0 space-y-2">
          <p className="text-[12px] text-muted-foreground">
            Allow / deny / unavailable — unavailable means infra fault, not a
            policy deny.
          </p>
          <EnforcementTable rows={data.enforcement} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-medium tabular-nums">{value}</div>
    </div>
  )
}

function EnforcementControls({
  mode,
  hardCapConfirm,
  setHardCapConfirm,
  onHardCap,
  onAlertOnly,
}: {
  mode: "alert_only" | "hard_cap"
  hardCapConfirm: boolean
  setHardCapConfirm: (v: boolean) => void
  onHardCap: () => void
  onAlertOnly: () => void
}) {
  if (mode === "alert_only") {
    if (hardCapConfirm) {
      return (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-destructive/35 bg-destructive/5 px-2.5 py-1.5 text-[12px]">
          <span>Hard cap can block production traffic.</span>
          <Button
            size="sm"
            variant="destructive"
            className="h-7"
            onClick={onHardCap}
          >
            Confirm
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7"
            onClick={() => setHardCapConfirm(false)}
          >
            Cancel
          </Button>
        </div>
      )
    }
    return (
      <Button
        size="sm"
        variant="outline"
        className="h-8"
        onClick={() => setHardCapConfirm(true)}
      >
        Enable hard cap…
      </Button>
    )
  }
  return (
    <Button size="sm" variant="outline" className="h-8" onClick={onAlertOnly}>
      Switch to alert only
    </Button>
  )
}

function PeriodPicker({
  budgets,
  selected,
  onSelect,
}: {
  budgets: BudgetPeriod[]
  selected: BudgetPeriod
  onSelect: (b: BudgetPeriod) => void
}) {
  return (
    <div className="flex gap-1 rounded-md border border-border p-0.5">
      {budgets.map((b) => (
        <button
          key={b.period_id}
          type="button"
          onClick={() => onSelect(b)}
          className={cn(
            "rounded px-2.5 py-1 text-[11px] tabular-nums transition-colors",
            selected.period_id === b.period_id
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {b.period_start.slice(0, 7)}
        </button>
      ))}
    </div>
  )
}

function RateCardsSection({
  data,
  selectedCard,
  setSelectedCard,
  versionId,
  setVersionId,
  version,
  modelProbe,
  setModelProbe,
  matched,
  showDryRun,
  setShowDryRun,
}: {
  data: typeof BILLING_V2
  selectedCard: RateCard
  setSelectedCard: (c: RateCard) => void
  versionId: string
  setVersionId: (id: string) => void
  version: RateCard["versions"][0]
  modelProbe: string
  setModelProbe: (v: string) => void
  matched: string | null
  showDryRun: boolean
  setShowDryRun: (v: boolean) => void
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
      <nav className="space-y-1">
        {data.rate_cards.map((c) => (
          <button
            key={c.card_id}
            type="button"
            onClick={() => setSelectedCard(c)}
            className={cn(
              "flex w-full flex-col rounded-lg border px-3 py-2.5 text-left transition-colors",
              selectedCard.card_id === c.card_id
                ? "border-foreground/30 bg-muted/50"
                : "border-transparent hover:bg-muted/30",
            )}
          >
            <span className="text-[13px] font-medium">{c.name}</span>
            <span className="mt-0.5 font-mono text-[10px] text-muted-foreground">
              {c.currency} · {c.status}
              {c.status === "published" ? ` · v${c.versions[0]?.version}` : ""}
            </span>
          </button>
        ))}
      </nav>

      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            {selectedCard.name}
          </CardTitle>
          <p className="text-[12px] text-muted-foreground">
            Versions immutable once created · publish new version only ·
            archive, never delete
          </p>
        </CardHeader>
        <CardContent className="space-y-4 px-4 py-3">
          {selectedCard.status === "archived" ? (
            <p className="text-[12px] text-muted-foreground">
              Archived — read-only historical audit.
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <span className="text-muted-foreground">Version</span>
            {selectedCard.versions.map((v) => (
              <button
                key={v.version_id}
                type="button"
                className={cn(
                  "h-7 rounded-md border px-2 font-mono text-[11px]",
                  versionId === v.version_id
                    ? "border-foreground bg-foreground text-background"
                    : "border-border",
                )}
                onClick={() => setVersionId(v.version_id)}
              >
                v{v.version}
              </button>
            ))}
            {selectedCard.status === "draft" ? (
              <Button
                size="sm"
                className="ml-auto h-7"
                onClick={() => setShowDryRun(true)}
              >
                Dry-run publish
              </Button>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border/60 px-3 py-2 text-[12px]">
            <span className="text-muted-foreground">Glob probe</span>
            <Input
              value={modelProbe}
              onChange={(e) => setModelProbe(e.target.value)}
              className="h-7 w-44 font-mono text-[12px]"
            />
            <span className="font-mono text-foreground">
              → {matched ?? "no match"}
            </span>
          </div>

          <PriceTable prices={version.prices} />

          {showDryRun ? (
            <div className="rounded-lg border border-border bg-muted/25 px-3 py-3">
              <div className="text-[13px] font-medium">
                Publish dry-run — EstimateCost replay
              </div>
              <p className="mt-0.5 text-[12px] text-muted-foreground">
                Pure cost math before commit.
              </p>
              <table className={cn(listTable.table, "mt-2")}>
                <thead>
                  <tr className={listTable.headRow}>
                    <th className={listTable.head}>request_id</th>
                    <th className={listTable.head}>model</th>
                    <th className={listTable.head}>pattern</th>
                    <th className={cn(listTable.head, "text-right")}>est ¢</th>
                  </tr>
                </thead>
                <tbody>
                  {data.dry_run_preview.map((r) => (
                    <tr key={r.request_id} className={listTable.row}>
                      <td className={cn(listTable.cell, listTable.mono)}>
                        {r.request_id}
                      </td>
                      <td className={cn(listTable.cell, listTable.mono)}>
                        {r.model}
                      </td>
                      <td
                        className={cn(
                          listTable.cell,
                          listTable.mono,
                          "text-[11px]",
                        )}
                      >
                        {r.matched_pattern_old} → {r.matched_pattern_new}
                      </td>
                      <td
                        className={cn(
                          listTable.cell,
                          listTable.mono,
                          "text-right tabular-nums",
                        )}
                      >
                        {r.estimated_cents_old} → {r.estimated_cents_new}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  className="h-7"
                  onClick={() => {
                    toast.success("Published new version")
                    setShowDryRun(false)
                  }}
                >
                  Commit publish
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7"
                  onClick={() => setShowDryRun(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function PriceTable({ prices }: { prices: RateCard["versions"][0]["prices"] }) {
  return (
    <table className={listTable.table}>
      <thead>
        <tr className={listTable.headRow}>
          <th className={listTable.head}>provider</th>
          <th className={listTable.head}>model_pattern</th>
          <th className={cn(listTable.head, "text-right")}>in ¢/1k</th>
          <th className={cn(listTable.head, "text-right")}>out ¢/1k</th>
        </tr>
      </thead>
      <tbody>
        {prices.map((p) => (
          <tr
            key={`${p.provider}-${p.model_pattern}`}
            className={listTable.row}
          >
            <td className={cn(listTable.cell, listTable.mono)}>{p.provider}</td>
            <td className={cn(listTable.cell, listTable.mono)}>
              {p.model_pattern}
            </td>
            <td
              className={cn(
                listTable.cell,
                listTable.mono,
                "text-right tabular-nums",
              )}
            >
              {p.input_cents_per_1k}
            </td>
            <td
              className={cn(
                listTable.cell,
                listTable.mono,
                "text-right tabular-nums",
              )}
            >
              {p.output_cents_per_1k}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function EnforcementTable({ rows }: { rows: EnforcementDecision[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border/70">
      <table className={listTable.table}>
        <thead>
          <tr className={listTable.headRow}>
            <th className={listTable.head}>When</th>
            <th className={listTable.head}>Decision</th>
            <th className={listTable.head}>Reason</th>
            <th className={listTable.head}>remaining</th>
            <th className={listTable.head}>request / trace</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.decision_id}
              className={cn(
                listTable.row,
                r.decision === "unavailable" && "bg-amber-500/5",
              )}
            >
              <td className={cn(listTable.cell, listTable.meta, "font-mono")}>
                {r.decided_at.replace("T", " ").slice(0, 16)}Z
              </td>
              <td className={listTable.cell}>
                <StatusDot
                  tone={
                    r.decision === "allow"
                      ? "ok"
                      : r.decision === "deny"
                        ? "error"
                        : "warn"
                  }
                  label={r.decision}
                />
                {r.decision === "unavailable" ? (
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    infra fault — not policy deny
                  </div>
                ) : null}
              </td>
              <td className={cn(listTable.cell, listTable.mono, "text-[12px]")}>
                {r.reason}
                {r.agent_slug ? (
                  <div className={listTable.meta}>{r.agent_slug}</div>
                ) : null}
              </td>
              <td
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {r.remaining_cents == null
                  ? "—"
                  : full.format(r.remaining_cents)}
              </td>
              <td className={cn(listTable.cell, listTable.mono, "text-[12px]")}>
                <Link
                  href={`/dashboard/billing?shape=request_point_lookup&request_id=${r.request_id}`}
                  className="hover:underline"
                >
                  {r.request_id}
                </Link>
                {r.trace_id ? (
                  <div>
                    <Link
                      href={`/dashboard/explore/t/${r.trace_id}`}
                      className="text-muted-foreground hover:underline"
                    >
                      {r.trace_id}
                    </Link>
                  </div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UsageShapeTable({
  rows,
}: {
  rows: {
    key: string
    label: string
    value: number
    estimated_cost_cents: number
    completeness: string
    request_id?: string
  }[]
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border/70">
      <table className={listTable.table}>
        <thead>
          <tr className={listTable.headRow}>
            <th className={listTable.head}>Row</th>
            <th className={listTable.head}>value</th>
            <th className={listTable.head}>estimated_cost</th>
            <th className={listTable.head}>completeness</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={listTable.row}>
              <td className={listTable.cell}>
                {r.request_id ? (
                  <Link
                    href={`/dashboard/explore?request_id=${r.request_id}`}
                    className={cn(listTable.mono, "hover:underline")}
                  >
                    {r.label}
                  </Link>
                ) : (
                  <span className={listTable.mono}>{r.label}</span>
                )}
              </td>
              <td
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {full.format(r.value)}
              </td>
              <td
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {usd(centsUsd(r.estimated_cost_cents))}
                <span className="ml-1 text-[10px] text-muted-foreground">
                  est.
                </span>
              </td>
              <td className={listTable.cell}>
                <StatusDot
                  tone={r.completeness === "complete" ? "ok" : "warn"}
                  label={r.completeness}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function BillingPage() {
  return (
    <DashboardShell>
      <BillingWorkbench />
    </DashboardShell>
  )
}
