<script setup lang="ts">
import { computed } from "vue"
import AnalyticsChart from "./AnalyticsChart.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import GovernSparkline from "@/components/console/govern/primitives/GovernSparkline.vue"
import { formatGovernDate, formatGovernNumber, formatGovernPercent, formatGovernShortDate } from "@/lib/govern-format"
import {
  METRIC_LABELS,
  analyticsDays,
  analyticsDenials,
  analyticsErrorRate,
  cacheHitPercent,
  formatMetric,
  metricSeries,
  metricTotal,
  type AnalyticsRange,
  type MetricKey,
} from "@/lib/analytics-preview"

const props = defineProps<{ range: AnalyticsRange; metric: MetricKey; asTable: boolean }>()

const points = computed(() => analyticsDays(props.range))
const labels = computed(() => points.value.map((point) => formatGovernShortDate(point.day)))
const values = computed(() => metricSeries(points.value, props.metric))

const perRequestSeries = computed(() =>
  points.value.map((point) => (point.requests === 0 ? 0 : point.spendUsd / point.requests)),
)
const cacheSeries = computed(() =>
  points.value.map((point) => (point.inputTokens === 0 ? 0 : (point.cachedTokens / point.inputTokens) * 100)),
)

const windowTotal = computed(() => metricTotal(points.value, props.metric))
const lastDay = computed(() => points.value.at(-1) ?? null)
const firstDay = computed(() => points.value[0] ?? null)

const changePercent = computed(() => {
  if (!firstDay.value || !lastDay.value || firstDay.value === lastDay.value) return null
  const before = firstDay.value[props.metric]
  if (before === 0) return null
  return ((lastDay.value[props.metric] - before) / before) * 100
})

const perRequest = computed(() => {
  const requests = metricTotal(points.value, "requests")
  const spend = metricTotal(points.value, "spendUsd")
  return requests === 0 ? 0 : spend / requests
})

function formatValue(value: number): string {
  return formatMetric(props.metric, value)
}

const chartColor = computed(() => {
  switch (props.metric) {
    case "spendUsd":
      return "var(--ix-s2)"
    case "requests":
      return "var(--ix-s1)"
    case "inputTokens":
    case "outputTokens":
      return "var(--ix-s3)"
    case "cachedTokens":
      return "var(--ix-s4)"
    case "reasoningTokens":
      return "var(--ix-s6)"
    default:
      return "var(--ix-s1)"
  }
})

const summary = computed(() => {
  const days = points.value
  if (days.length < 2) return "Needs at least two recorded days before a trend can be described."
  const ranked = [...days].sort((left, right) => right[props.metric] - left[props.metric])
  const peak = ranked[0]
  const trough = ranked.at(-1)
  const last = lastDay.value
  if (!peak || !trough || !last) return "Needs at least two recorded days before a trend can be described."
  return [
    `${formatMetric(props.metric, windowTotal.value)} across ${days.length} recorded days.`,
    `Peak ${formatMetric(props.metric, peak[props.metric])} on ${formatGovernDate(peak.day)}.`,
    `Lowest ${formatMetric(props.metric, trough[props.metric])} on ${formatGovernDate(trough.day)}.`,
    `Last recorded day ${formatMetric(props.metric, last[props.metric])} on ${formatGovernDate(last.day)}.`,
  ].join(" ")
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <GovernStatTile
        :label="`${METRIC_LABELS[metric]} in window`"
        :value="formatMetric(metric, windowTotal)"
        helper="Sum of the recorded days only"
      >
        <GovernSparkline :points="values" :label="`${METRIC_LABELS[metric]} trend`" :width="120" :height="24" />
      </GovernStatTile>
      <GovernStatTile
        label="Change across the window"
        :value="changePercent === null ? 'Not comparable' : formatGovernPercent(changePercent)"
        helper="First recorded day against the last"
        :tone="changePercent !== null && changePercent > 15 ? 'warning' : 'default'"
      >
        <GovernSparkline :points="values" :label="`${METRIC_LABELS[metric]} change`" :width="120" :height="24" />
      </GovernStatTile>
      <GovernStatTile
        label="Spend per request"
        :value="`$${perRequest.toFixed(3)}`"
        helper="Derived from the same fixture series"
      >
        <GovernSparkline :points="perRequestSeries" label="Spend per request trend" :width="120" :height="24" />
      </GovernStatTile>
      <GovernStatTile
        label="Cache hit share"
        :value="formatGovernPercent(cacheHitPercent(points))"
        helper="Cached tokens over all prompt tokens"
      >
        <GovernSparkline :points="cacheSeries" label="Cache hit share trend" :width="120" :height="24" />
      </GovernStatTile>
    </div>

    <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
      <AnalyticsChart
        :values="values"
        :labels="labels"
        :label="`${METRIC_LABELS[metric]} per recorded day`"
        :format="formatValue"
        :color="chartColor"
      />
      <p class="mt-1 text-[0.6875rem] leading-4 text-fg-3">{{ summary }}</p>
    </div>

    <div v-if="asTable" class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-table" aria-label="Daily usage values behind the chart">
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col" class="text-right">Requests</th>
            <th scope="col" class="text-right">Spend</th>
            <th scope="col" class="text-right">Input</th>
            <th scope="col" class="text-right">Output</th>
            <th scope="col" class="text-right">Cached</th>
            <th scope="col" class="text-right">Reasoning</th>
            <th scope="col" class="text-right">Errors</th>
            <th scope="col" class="text-right">Policy denials</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in points" :key="point.day">
            <th scope="row" class="text-left font-mono text-[0.6875rem] font-normal text-fg-2">{{ point.day }}</th>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatGovernNumber(point.requests) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatMetric("spendUsd", point.spendUsd) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatMetric("inputTokens", point.inputTokens) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatMetric("outputTokens", point.outputTokens) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatMetric("cachedTokens", point.cachedTokens) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ formatMetric("reasoningTokens", point.reasoningTokens) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ point.errors }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ point.policyDenials }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg border border-line-subtle bg-surface-1 px-3 py-2 text-xs text-fg-2">
      <span>
        Error rate
        <span class="ml-1 font-mono text-fg-1 tabular-nums">{{ formatGovernPercent(analyticsErrorRate(points), 2) }}</span>
      </span>
      <span>
        Runs refused by budget or policy
        <span class="ml-1 font-mono text-fg-1 tabular-nums">{{ formatGovernNumber(analyticsDenials(points)) }}</span>
      </span>
      <span class="text-[0.6875rem] text-fg-3">
        Refusals are counted where they were recorded, not inferred from missing requests.
      </span>
    </div>

    <GovernCaveat tone="info" title="Why the axis starts where it does">
      The chart's floor is derived from the fixture series itself, not from zero, so day-to-day movement is readable.
      Turn on the day-by-day values to read the exact numbers; the picture is never the only way to read them.
    </GovernCaveat>
  </div>
</template>
