<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { RefreshCw } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import CompositionBar from "@/components/console/CompositionBar.vue"
import MiniBarChart from "@/components/console/MiniBarChart.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import IxVerdict from "@/components/console/IxVerdict.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import OverviewAttentionPanel from "./OverviewAttentionPanel.vue"
import OverviewRunsPanel from "./OverviewRunsPanel.vue"
import OverviewSourcesPanel from "./OverviewSourcesPanel.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { useConsoleDemo } from "@/composables/useConsoleDemo"
import { formatGovernClock, formatGovernStamp } from "@/lib/govern-format"
import { DEMO_CONTEXT, DEMO_OVERVIEW, DEMO_PLATFORM_HEALTH, DEMO_TRACE_LIST } from "@/lib/console-demo"
import {
  OVERVIEW_TAB_LABELS,
  OVERVIEW_TAB_MEANING,
  overviewHref,
  type OverviewState,
  type OverviewTab,
} from "@/lib/govern-query"
import { isOperatorAuthError, operatorFailureDetail } from "@/lib/operator-error"
import {
  OVERVIEW_CONTRACT,
  OVERVIEW_NOTES,
  OVERVIEW_RUNS_LIMIT,
  buildOverviewAttention,
  buildOverviewSources,
  overviewStaleness,
  overviewTiles,
  overviewVerdict,
  type OverviewFlags,
} from "@/lib/overview-view"

const props = defineProps<{ state: OverviewState }>()
const emit = defineEmits<{ update: [state: OverviewState] }>()

const contextState = useOperatorContext()
const overviewState = useOperatorOverview()
const healthState = usePlatformHealth()
const tracesState = useTraceList(new URLSearchParams(`limit=${OVERVIEW_RUNS_LIMIT}`))

const demo = useConsoleDemo()
const context = computed(() => contextState.data.value ?? (demo.value ? DEMO_CONTEXT : null))
const overview = computed(() => overviewState.data.value ?? (demo.value ? DEMO_OVERVIEW : null))
const health = computed(() => healthState.data.value ?? (demo.value ? DEMO_PLATFORM_HEALTH : null))
const traces = computed(() => tracesState.data.value ?? (demo.value ? DEMO_TRACE_LIST : null))
const demoActive = computed(
  () => demo.value && (!overviewState.data.value || !healthState.data.value || !tracesState.data.value),
)

const refreshing = ref(false)

/* The page reads live data, so ages are measured against a clock the page owns and re-ticks. */
const nowMs = ref<number | null>(null)
let clock: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  nowMs.value = Date.now()
  clock = setInterval(() => {
    nowMs.value = Date.now()
  }, 15_000)
})
onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})

const authIssue = computed(
  () =>
    !demoActive.value &&
    (isOperatorAuthError(overviewState.error.value) ||
      isOperatorAuthError(contextState.error.value) ||
      isOperatorAuthError(healthState.error.value)),
)
const loading = computed(() => !overview.value && !demoActive.value && !overviewState.error.value && overviewState.status.value === "pending")
const healthLoading = computed(() => !health.value && !demoActive.value && !healthState.error.value && healthState.status.value === "pending")
const tracesLoading = computed(() => !traces.value && !demoActive.value && !tracesState.error.value && tracesState.status.value === "pending")

const failureDetail = computed(() =>
  !demoActive.value && overviewState.error.value && !authIssue.value ? operatorFailureDetail(overviewState.error.value) : null,
)

const staleness = computed(() => overviewStaleness(health.value?.observed_at ?? null, nowMs.value))

const issues = computed(() =>
  buildOverviewAttention({
    health: health.value,
    traces: traces.value,
    staleness: staleness.value,
    healthFailed: !demoActive.value && Boolean(healthState.error.value),
    tracesFailed: !demoActive.value && Boolean(tracesState.error.value),
  }),
)

const flags = computed<OverviewFlags>(() => ({
  hasOverview: Boolean(overview.value),
  hasHealth: Boolean(health.value),
  hasTraces: Boolean(traces.value),
  authIssue: authIssue.value,
  loading: loading.value || healthLoading.value,
}))

const verdict = computed(() =>
  overviewVerdict({ flags: flags.value, issues: issues.value, health: health.value, staleness: staleness.value }),
)

const verdictTone = computed(() => {
  if (verdict.value.tone === "ok") return "healthy" as const
  if (verdict.value.tone === "warning") return "attention" as const
  return "unknown" as const
})

const tiles = computed(() => overviewTiles({ overview: overview.value, health: health.value, traces: traces.value }))

const runSegments = computed(() => {
  const items = traces.value?.items ?? []
  const ok = items.filter((trace) => trace.status === "ok").length
  return [
    { label: "OK", value: ok, color: "bg-s1" },
    { label: "Error", value: items.length - ok, color: "bg-crit" },
  ]
})

const dependencySegments = computed(() => {
  const values = Object.values(health.value?.dependency_health ?? {})
  return [
    { label: "Ok", value: values.filter((value) => value === "ok").length, color: "bg-s1" },
    { label: "Degraded", value: values.filter((value) => value === "degraded").length, color: "bg-warn" },
    { label: "Unavailable", value: values.filter((value) => value === "unavailable").length, color: "bg-crit" },
  ]
})

const orderedRuns = computed(() =>
  [...(traces.value?.items ?? [])]
    .sort((left, right) => Date.parse(left.started_at) - Date.parse(right.started_at))
    .slice(-8),
)
const runDurations = computed(() => orderedRuns.value.map((trace) => trace.duration_ms ?? 0))
const runDurationLabels = computed(() => orderedRuns.value.map((trace) => formatGovernClock(trace.started_at)))

const agentSegments = computed(() => {
  const total = overview.value?.counts.agents ?? 0
  const active = overview.value?.counts.active_agents ?? 0
  return [
    { label: "Active", value: active, color: "bg-s1" },
    { label: "Inactive", value: Math.max(0, total - active), color: "bg-fg-off" },
  ]
})

const sources = computed(() =>
  buildOverviewSources({
    context: context.value,
    overview: overview.value,
    health: health.value,
    traces: traces.value,
    healthFailed: !demoActive.value && Boolean(healthState.error.value),
    tracesFailed: !demoActive.value && Boolean(tracesState.error.value),
    loading: loading.value || healthLoading.value || tracesLoading.value,
  }),
)

const settled = computed(() => !loading.value && !healthLoading.value && !tracesLoading.value)

const snapshotLabel = computed(() => {
  if (!health.value) return "No platform snapshot has been read on this visit, so no finding is claimed."
  return `Read ${staleness.value.label} (${formatGovernStamp(health.value.observed_at)}). Findings below restate only what that read reported.`
})

const tabs = [
  { id: "attention", label: OVERVIEW_TAB_LABELS.attention },
  { id: "runs", label: OVERVIEW_TAB_LABELS.runs },
  { id: "sources", label: OVERVIEW_TAB_LABELS.sources },
]

const badges = computed<Record<string, string>>(() => ({
  attention: String(issues.value.length),
  runs: traces.value ? String(traces.value.items.length) : "—",
  sources: `${sources.value.filter((source) => source.state === "ok").length}/${sources.value.length}`,
}))

const headerState = computed<"live" | "partial" | "illustrative">(() =>
  demoActive.value ? "illustrative" : overview.value && health.value && !authIssue.value ? "live" : "partial",
)
const observedAt = computed(() => {
  const stamps = [
    health.value?.observed_at,
    overview.value?.observed_at,
    context.value?.observed_at,
    traces.value?.observed_at,
  ].filter((stamp): stamp is string => Boolean(stamp))
  if (!stamps.length) return null
  return stamps.reduce((newest, stamp) => (Date.parse(stamp) > Date.parse(newest) ? stamp : newest))
})
const scopeText = computed(() => {
  const slug = overview.value?.org_slug ?? context.value?.org_slug
  if (demoActive.value) return slug ? `${slug} · illustrative development read` : "Illustrative development read"
  return slug ? `${slug} · tenant-scoped read` : "Organization not verified"
})
const rangeText = computed(() =>
  traces.value
    ? `One read per load · newest ${OVERVIEW_RUNS_LIMIT} runs · server window ${formatGovernStamp(traces.value.query_start)} → ${formatGovernStamp(traces.value.query_end)}`
    : `One read per load · newest ${OVERVIEW_RUNS_LIMIT} runs · no window observed`,
)

const headerVerdict = computed(() => {
  if (demoActive.value) {
    return "Illustrative development data. The operator API is not connected in this environment, so this page is showing recorded design fixtures. It is not a live organization read and makes no production claim."
  }
  if (failureDetail.value) {
    return `${verdict.value.text} ${failureDetail.value} No preview or fixture organization is substituted for this gap.`
  }
  return `${verdict.value.text} Every value comes from a live tenant-scoped read on this visit; nothing here is carried over from an earlier read or from a preview fixture.`
})

function update(patch: Partial<OverviewState>): void {
  emit("update", { ...props.state, ...patch })
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.allSettled([
      contextState.refresh(),
      overviewState.refresh(),
      healthState.refresh(),
      tracesState.refresh(),
    ])
    nowMs.value = Date.now()
  } finally {
    refreshing.value = false
  }
}

function openRun(runId: string): void {
  void navigateTo(`/explore/r/${encodeURIComponent(runId)}?return=%2F`)
}

function goto(href: string): void {
  void navigateTo(href)
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${overviewHref(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  keys: {
    r: refreshAll,
    y: copyCurrentLink,
    "1": () => update({ tab: "attention" }),
    "2": () => update({ tab: "runs" }),
    "3": () => update({ tab: "sources" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "1 / 2 / 3", label: "Needs attention · Recent runs · Sources" },
      { keys: "j / k", label: "Move through the run rows (on the runs view)" },
      { keys: "Enter", label: "Open the selected run in Explore" },
      { keys: "r", label: "Re-read every source on this page" },
      { keys: "y", label: "Copy link to this view" },
      { keys: "g x", label: "Go to Explore" },
      { keys: "g n", label: "Go to Analytics" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <ConsolePageHeader
      title="Overview"
      definition="What the platform reported for this organization at the moment this page was read — the counts it owns, the dependency states it checks, and the newest run records it published."
      :state="headerState"
      :observed="observedAt ? formatGovernStamp(observedAt) : undefined"
      :scope="scopeText"
      :contract="OVERVIEW_CONTRACT"
      :verdict="headerVerdict"
      :range="rangeText"
      coverage="3 live contracts read · no evidence-coverage contract connected"
      :notes="OVERVIEW_NOTES"
    >
      <template #actions>
        <span class="sr-only" aria-live="polite">{{ refreshing ? "Re-reading the overview sources" : "" }}</span>
        <button type="button" class="ix-button-secondary" :disabled="refreshing" @click="refreshAll">
          <RefreshCw :size="14" :stroke-width="1.75" :class="refreshing && 'animate-spin'" aria-hidden="true" />
          Re-read
        </button>
      </template>
      <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
        <span class="text-fg-2">{{ overview?.org_name ?? context?.org_name ?? "Organization not verified" }}</span>
        <span v-if="overview?.org_slug" class="font-mono"> · {{ overview.org_slug }}</span>
        <span aria-hidden="true">·</span>
        <span>Health <span :class="staleness.stale ? 'text-warn' : 'text-fg-2'">{{ staleness.label }}</span></span>
      </p>
    </ConsolePageHeader>

    <IxVerdict
      :tone="verdictTone"
      eyebrow="Current read"
      :title="verdict.text"
      :body="verdict.caveat ?? undefined"
      :meta="observedAt ? formatGovernStamp(observedAt) : undefined"
    />

    <section class="grid grid-cols-2 gap-2 xl:grid-cols-4" aria-label="What this read reported">
      <GovernStatTile
        v-for="tile in tiles"
        :key="tile.label"
        :label="tile.label"
        :value="tile.value"
        :helper="tile.helper"
        :tone="tile.tone"
        compact
      />
    </section>

    <section class="grid gap-3 sm:grid-cols-3" aria-label="Snapshot composition">
      <div class="console-panel p-3">
        <CompositionBar title="Run outcome" :segments="runSegments" />
      </div>
      <div class="console-panel p-3">
        <CompositionBar title="Dependency state" :segments="dependencySegments" />
      </div>
      <div class="console-panel p-3">
        <CompositionBar title="Agent inventory" :segments="agentSegments" />
      </div>
    </section>

    <div v-if="traces?.items.length" class="console-panel p-3">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="text-[0.6875rem] font-medium text-fg-3">Run duration</h3>
        <span class="font-mono text-[0.6875rem] text-fg-3">ms</span>
      </div>
      <MiniBarChart
        class="mt-2"
        :values="runDurations"
        :labels="runDurationLabels"
        label="Duration of the newest runs on this page"
        color="var(--ix-s1)"
        :height="96"
      />
    </div>

    <GovernTabBar
      :tabs="tabs"
      :model-value="state.tab"
      :badges="badges"
      aria-label="Overview sections"
      @update:model-value="update({ tab: $event as OverviewTab })"
    />

    <p class="-mt-1 max-w-3xl text-[0.6875rem] leading-4 text-fg-3">{{ OVERVIEW_TAB_MEANING[state.tab] }}</p>

    <OverviewAttentionPanel
      v-if="state.tab === 'attention'"
      :rows="issues"
      :settled="settled"
      :snapshot-label="snapshotLabel"
      @open="goto"
    />
    <OverviewRunsPanel
      v-else-if="state.tab === 'runs'"
      :traces="traces"
      :loading="tracesLoading"
      :failed="Boolean(tracesState.error.value) && !traces"
      :auth-issue="isOperatorAuthError(tracesState.error.value)"
      :now-ms="nowMs"
      @open-run="openRun"
      @goto="goto"
      @refresh="refreshAll"
    />
    <OverviewSourcesPanel
      v-else
      :sources="sources"
      :context="context"
      :now-ms="nowMs"
      :stream-enabled="Boolean(overview)"
    />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
