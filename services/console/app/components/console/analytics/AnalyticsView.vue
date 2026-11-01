<script setup lang="ts">
import { computed, ref } from "vue"
import AnalyticsBreakdownPanel from "./AnalyticsBreakdownPanel.vue"
import AnalyticsHeader from "./AnalyticsHeader.vue"
import AnalyticsLatencyPanel from "./AnalyticsLatencyPanel.vue"
import AnalyticsUsagePanel from "./AnalyticsUsagePanel.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernShortcutsDialog from "@/components/console/govern/primitives/GovernShortcutsDialog.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import GovernCopyId from "@/components/console/govern/primitives/GovernCopyId.vue"
import { useGovernShortcuts } from "@/composables/useGovernShortcuts"
import { formatGovernDate, formatGovernPercent } from "@/lib/govern-format"
import {
  ANALYTICS_TAB_LABELS,
  analyticsHref,
  type AnalyticsListState,
  type AnalyticsTab,
} from "@/lib/govern-query"
import {
  ANALYTICS_DAYS,
  ANALYTICS_USAGE_CONTRACT,
  DIMENSIONS,
  DIMENSION_LABELS,
  METRIC_KEYS,
  METRIC_LABELS,
  analyticsCoverageText,
  analyticsDays,
  analyticsIsPartial,
  formatMetric,
  metricTotal,
  type AnalyticsRange,
  type Dimension,
  type MetricKey,
} from "@/lib/analytics-preview"

const props = defineProps<{ state: AnalyticsListState }>()
const emit = defineEmits<{ update: [state: AnalyticsListState] }>()

function update(patch: Partial<AnalyticsListState>): void {
  emit("update", { ...props.state, ...patch })
}

const header = ref<InstanceType<typeof AnalyticsHeader> | null>(null)

const points = computed(() => analyticsDays(props.state.range))
const partial = computed(() => analyticsIsPartial(props.state.range))

const tabs = [
  { id: "usage", label: ANALYTICS_TAB_LABELS.usage },
  { id: "latency", label: ANALYTICS_TAB_LABELS.latency },
  { id: "breakdown", label: ANALYTICS_TAB_LABELS.breakdown },
]

const metricOptions = METRIC_KEYS.map((key) => ({ value: key, label: METRIC_LABELS[key] }))
const dimensionOptions = DIMENSIONS.map((dimension) => ({ value: dimension, label: DIMENSION_LABELS[dimension] }))

const windowSpend = computed(() => formatMetric("spendUsd", metricTotal(points.value, "spendUsd")))
const windowRequests = computed(() => formatMetric("requests", metricTotal(points.value, "requests")))
const recordedSpan = computed(() => {
  const first = ANALYTICS_DAYS[0]
  const last = ANALYTICS_DAYS.at(-1)
  if (!first || !last) return "no recorded days"
  return `${formatGovernDate(first.day)} to ${formatGovernDate(last.day)}`
})

const worstDay = computed(() => {
  const ranked = [...points.value].sort(
    (left, right) => right.errors / right.requests - left.errors / left.requests,
  )
  const worst = ranked[0]
  if (!worst || worst.requests === 0) return null
  return `${formatGovernDate(worst.day)} at ${formatGovernPercent((worst.errors / worst.requests) * 100, 2)}`
})

function toggleTable(): void {
  update({ asTable: !props.state.asTable })
}

function copyCurrentLink(): void {
  if (!import.meta.client) return
  void navigator.clipboard.writeText(`${window.location.origin}${analyticsHref(props.state)}`)
}

const { helpOpen } = useGovernShortcuts({
  keys: {
    y: copyCurrentLink,
    t: toggleTable,
    "1": () => update({ tab: "usage" }),
    "2": () => update({ tab: "latency" }),
    "3": () => update({ tab: "breakdown" }),
  },
})

const shortcutGroups = [
  {
    title: "This page",
    rows: [
      { keys: "1 / 2 / 3", label: "Usage · Latency · By dimension" },
      { keys: "t", label: "Show or hide the day-by-day values" },
      { keys: "y", label: "Copy link to this view" },
      { keys: "g e", label: "Go to evidence" },
      { keys: "g b", label: "Go to budgets" },
      { keys: "?", label: "Show this sheet" },
    ],
  },
]
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-3 pb-2">
    <AnalyticsHeader ref="header" :range="state.range" @update:range="update({ range: $event as AnalyticsRange })" />

    <section class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[0.6875rem] text-fg-3" aria-label="Window summary">
      <span :class="partial ? 'text-warn' : 'text-fg-3'">{{ analyticsCoverageText(state.range) }}</span>
      <span>
        Window: <span class="font-mono text-fg-2 tabular-nums">{{ windowRequests }}</span> requests ·
        <span class="font-mono text-fg-2 tabular-nums">{{ windowSpend }}</span>
      </span>
      <span v-if="worstDay">Worst recorded error day: {{ worstDay }}</span>
      <span>Recorded days available: {{ recordedSpan }}</span>
      <GovernCopyId :id="ANALYTICS_USAGE_CONTRACT" label="Usage contract" truncate />
    </section>

    <GovernTabBar :tabs="tabs" :model-value="state.tab" aria-label="Analytics views" @update:model-value="update({ tab: $event as AnalyticsTab })" />

    <div class="flex flex-wrap items-center gap-2">
      <GovernFilterSelect
        v-if="state.tab === 'usage'"
        label="Metric"
        :model-value="state.metric"
        :options="metricOptions"
        default-value="spendUsd"
        @update:model-value="update({ metric: $event as MetricKey })"
      />
      <GovernFilterSelect
        v-if="state.tab === 'breakdown'"
        label="Split by"
        :model-value="state.dimension"
        :options="dimensionOptions"
        default-value="provider"
        @update:model-value="update({ dimension: $event as Dimension })"
      />
      <GovernFilterSelect
        v-if="state.tab !== 'breakdown'"
        label="Values"
        :model-value="state.asTable ? 'table' : 'chart'"
        :options="[
          { value: 'chart', label: 'Chart only' },
          { value: 'table', label: 'Chart and table' },
        ]"
        default-value="chart"
        @update:model-value="update({ asTable: $event === 'table' })"
      />
      <button
        v-if="state.tab !== 'breakdown'"
        type="button"
        class="text-[0.6875rem] text-fg-3 underline decoration-line-strong underline-offset-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        @click="toggleTable"
      >
        {{ state.asTable ? "Hide the day-by-day values" : "Show the day-by-day values" }} (t)
      </button>
    </div>

    <AnalyticsUsagePanel v-if="state.tab === 'usage'" :range="state.range" :metric="state.metric" :as-table="state.asTable" />
    <AnalyticsLatencyPanel v-else-if="state.tab === 'latency'" :range="state.range" :as-table="state.asTable" />
    <AnalyticsBreakdownPanel v-else :range="state.range" :dimension="state.dimension" />

    <GovernShortcutsDialog v-model:open="helpOpen" :groups="shortcutGroups" />
  </div>
</template>
