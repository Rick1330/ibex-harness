<script setup lang="ts">
import { computed } from "vue"
import AnalyticsChart from "./AnalyticsChart.vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernNumber, formatGovernShortDate } from "@/lib/govern-format"
import {
  ANALYTICS_SLO_PENDING,
  ANALYTICS_USAGE_CONTRACT,
  analyticsDays,
  latencyBands,
  latencySeries,
  type AnalyticsRange,
} from "@/lib/analytics-preview"

const props = defineProps<{ range: AnalyticsRange; asTable: boolean }>()

const points = computed(() => analyticsDays(props.range))
const labels = computed(() => points.value.map((point) => formatGovernShortDate(point.day)))
const bands = computed(() => latencyBands(points.value))

const p95 = computed(() => latencySeries(points.value, "p95Ms"))
const overhead = computed(() => points.value.map((point) => point.proxyOverheadP95Ms))
const assembly = computed(() => points.value.map((point) => point.contextAssemblyP95Ms))

const lastBand = computed(() => bands.value.find((band) => band.label === "End to end") ?? null)
const platformShare = computed(() => {
  if (!lastBand.value || lastBand.value.p95 === 0) return 0
  const platform = bands.value.filter((band) => band.label !== "Provider time" && band.label !== "End to end")
  return (platform.reduce((sum, band) => sum + band.p95, 0) / lastBand.value.p95) * 100
})

function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${formatGovernNumber(Math.round(value))}ms`
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernCaveat tone="warning" title="These percentiles describe one recorded day">
      {{ ANALYTICS_SLO_PENDING }} Only end-to-end latency is measured at p50, p95 and p99. The other bands are a recorded
      p95 split of that same day, so their p50 and p99 read "Not recorded" instead of being scaled from a distribution
      nobody measured. A split is arithmetic on one figure, not three independent measurements.
    </GovernCaveat>

    <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-table" style="min-width: 640px" aria-label="Latency bands for the newest recorded day">
        <thead>
          <tr>
            <th scope="col">Band</th>
            <th scope="col" class="text-right">p50</th>
            <th scope="col" class="text-right">p95</th>
            <th scope="col" class="text-right">p99</th>
            <th scope="col">What it covers</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="band in bands" :key="band.label">
            <th scope="row" class="text-left text-xs font-medium text-fg-1">{{ band.label }}</th>
            <td class="text-right font-mono text-xs tabular-nums" :class="band.p50 === null ? 'text-fg-3' : 'text-fg-2'" :title="band.p50 === null ? 'Only the p95 split of this band is recorded' : ''">
              {{ band.p50 === null ? "Not recorded" : ms(band.p50) }}
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ ms(band.p95) }}</td>
            <td class="text-right font-mono text-xs tabular-nums" :class="band.p99 === null ? 'text-fg-3' : band.label === 'End to end' ? 'text-warn' : 'text-fg-2'" :title="band.p99 === null ? 'Only the p95 split of this band is recorded' : ''">
              {{ band.p99 === null ? "Not recorded" : ms(band.p99) }}
            </td>
            <td class="text-xs leading-4 text-fg-3">{{ band.meaning }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">
      On the newest recorded day, the platform's own bands account for {{ platformShare.toFixed(0) }}% of end-to-end p95;
      the rest is provider time.
    </p>

    <div class="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
        <AnalyticsChart :values="p95" :labels="labels" label="End-to-end p95 per recorded day" :format="ms" :height="180" />
      </div>
      <div class="rounded-lg border border-line-subtle bg-surface-1 p-3">
        <AnalyticsChart
          :values="overhead"
          :labels="labels"
          label="Proxy overhead p95 per recorded day"
          :format="ms"
          :height="180"
        />
        <div class="mt-2 border-t border-line-subtle pt-2">
          <AnalyticsChart
            :values="assembly"
            :labels="labels"
            label="Context assembly p95 per recorded day"
            :format="ms"
            :height="120"
          />
        </div>
      </div>
    </div>

    <div v-if="asTable" class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-table" aria-label="Daily latency values behind the charts">
        <thead>
          <tr>
            <th scope="col" rowspan="2" class="text-left align-bottom">Day</th>
            <th scope="colgroup" colspan="3" class="border-b border-line-subtle text-right">Measured end to end</th>
            <th scope="colgroup" colspan="3" class="border-b border-line-subtle text-right">Recorded as a p95 split</th>
          </tr>
          <tr>
            <th scope="col" class="text-right">p50</th>
            <th scope="col" class="text-right">p95</th>
            <th scope="col" class="text-right">p99</th>
            <th scope="col" class="text-right">Proxy</th>
            <th scope="col" class="text-right">Assembly</th>
            <th scope="col" class="text-right">Provider</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in points" :key="point.day">
            <th scope="row" class="text-left font-mono text-[0.6875rem] font-normal text-fg-2">{{ point.day }}</th>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.p50Ms) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.p95Ms) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.p99Ms) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.proxyOverheadP95Ms) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.contextAssemblyP95Ms) }}</td>
            <td class="text-right font-mono text-xs tabular-nums">{{ ms(point.providerP95Ms) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <GovernPendingData
      title="Measured p99 against the objective"
      :contract="ANALYTICS_USAGE_CONTRACT"
      description="A service objective needs a measured window with certified samples. Neither exists on this surface, so the honest answer is that the objective is not being evaluated here."
    />
  </div>
</template>
