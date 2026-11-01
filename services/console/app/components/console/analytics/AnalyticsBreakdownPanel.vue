<script setup lang="ts">
import { computed } from "vue"
import GovernCaveat from "@/components/console/govern/primitives/GovernCaveat.vue"
import BrandIcon from "@/components/console/BrandIcon.vue"
import GovernPendingData from "@/components/console/govern/primitives/GovernPendingData.vue"
import { formatGovernNumber, formatGovernPercent } from "@/lib/govern-format"
import {
  ANALYTICS_USAGE_CONTRACT,
  DIMENSION_LABELS,
  analyticsBreakdown,
  analyticsDays,
  analyticsMovers,
  breakdownSpendTotal,
  breakdownUnattributed,
  formatMetric,
  metricTotal,
  type AnalyticsRange,
  type BreakdownSlice,
  type Dimension,
} from "@/lib/analytics-preview"

const props = defineProps<{ range: AnalyticsRange; dimension: Dimension }>()

const points = computed(() => analyticsDays(props.range))
const rows = computed(() => analyticsBreakdown(props.dimension, points.value))
const movers = computed(() => analyticsMovers(props.dimension, points.value).slice(0, 3))
const unattributed = computed(() => breakdownUnattributed(rows.value))

const windowSpend = computed(() => metricTotal(points.value, "spendUsd"))
const reconcilesWithin = computed(() => Math.abs(breakdownSpendTotal(rows.value) - windowSpend.value) < 1)

const topShare = computed(() => rows.value.reduce((best, row) => (row.spendSharePercent > best ? row.spendSharePercent : best), 0))

/** Bars are scaled against the largest row, not the window, so a small share is still readable. */
function barWidth(row: BreakdownSlice): string {
  return `${topShare.value === 0 ? 0 : (row.spendSharePercent / topShare.value) * 100}%`
}

function deltaClass(value: number | null): string {
  if (value === null) return "text-fg-3"
  if (value > 10) return "text-warn"
  if (value < -10) return "text-ok"
  return "text-fg-2"
}

function deltaText(row: BreakdownSlice): string {
  if (row.deltaPercent === null) return "Not recorded"
  const text = formatGovernPercent(Math.abs(row.deltaPercent), 1)
  if (row.deltaPercent === 0) return text
  return row.deltaPercent > 0 ? `+${text}` : `−${text}`
}

function deltaTitle(row: BreakdownSlice): string {
  if (row.deltaPercent !== null) return "Change in spend against the previous window of the same length"
  return "No prior window exists for this row, so movement cannot be computed — it is not a zero change"
}

const summary = computed(() => {
  const lead = rows.value[0]
  if (!lead) return ""
  return `${lead.name} carries ${formatGovernPercent(lead.spendSharePercent, 1)} of ${formatMetric("spendUsd", windowSpend.value)} in this window across ${formatGovernNumber(lead.requests)} requests. ${rows.value.length} rows, ${unattributed.value.length > 0 ? `${unattributed.value.reduce((sum, row) => sum + row.spendSharePercent, 0).toFixed(1)}% unattributed` : "all attributed"}.`
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <GovernCaveat tone="info" :title="`Splits by ${DIMENSION_LABELS[dimension].toLowerCase()} are derived from a projection`">
      The share is the fixture; the amounts are that share applied to the same window total the usage tab sums, so the two
      panels reconcile. No row here comes from a certified billing record, and a model name is whatever the proxy forwarded
      — not a verified upstream answer.
    </GovernCaveat>

    <div class="ix-scroll overflow-x-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table table-fixed" style="min-width: 980px" :aria-label="`Spend split by ${DIMENSION_LABELS[dimension].toLowerCase()}`">
        <thead>
          <tr>
            <th scope="col" style="width: 220px">{{ DIMENSION_LABELS[dimension] }}</th>
            <th scope="col" style="width: 260px">Share of window spend</th>
            <th scope="col" style="width: 110px" class="text-right">Spend</th>
            <th scope="col" style="width: 110px" class="text-right">Requests</th>
            <th scope="col" style="width: 110px" class="text-right">Spend / request</th>
            <th scope="col" style="width: 140px" class="text-right">Spend change vs prior</th>
            <th scope="col" style="width: 96px">Source</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>
              <p class="flex items-center gap-1.5 truncate text-xs font-medium text-fg-1" :title="row.name"><BrandIcon :id="row.name" :size="14" /><span class="truncate">{{ row.name }}</span></p>
              <p class="mt-0.5 truncate font-mono text-[0.625rem] leading-4 text-fg-3" :title="row.id">{{ row.id }}</p>
            </td>
            <td>
              <span
                class="block h-2 overflow-hidden rounded-full bg-surface-2"
                role="img"
                :aria-label="`${formatGovernPercent(row.spendSharePercent, 1)} of window spend`"
              >
                <span class="block h-2 rounded-full bg-s1" :style="{ width: barWidth(row) }" />
              </span>
              <span class="mt-1 flex gap-x-3 font-mono text-[0.625rem] leading-4 text-fg-3 tabular-nums">
                <span>{{ formatGovernPercent(row.spendSharePercent, 1) }} spend</span>
                <span>{{ formatGovernPercent(row.requestSharePercent, 1) }} requests</span>
              </span>
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatMetric("spendUsd", row.spendUsd) }}</td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">{{ formatGovernNumber(row.requests) }}</td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">
              {{ row.requests === 0 ? "Not recorded" : `$${(row.spendUsd / row.requests).toFixed(3)}` }}
            </td>
            <td class="text-right font-mono text-xs tabular-nums" :class="deltaClass(row.deltaPercent)" :title="deltaTitle(row)">
              {{ deltaText(row) }}
            </td>
            <td>
              <span
                class="inline-flex items-center rounded-full border border-line-subtle px-1.5 py-0.5 text-[0.625rem] leading-4 text-fg-3"
                :title="
                  row.certainty === 'derived'
                    ? 'From a projection over trace metadata. It cannot support a bill or a dispute.'
                    : 'From a certified record.'
                "
              >
                {{ row.certainty === "derived" ? "Derived" : "Certified" }}
              </span>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" class="text-left text-xs font-medium text-fg-2">Total shown</th>
            <td class="font-mono text-[0.625rem] leading-4 text-fg-3">
              {{ formatGovernPercent(rows.reduce((sum, row) => sum + row.spendSharePercent, 0), 1) }} of window
            </td>
            <td class="text-right font-mono text-xs text-fg-1 tabular-nums">
              {{ formatMetric("spendUsd", breakdownSpendTotal(rows)) }}
            </td>
            <td class="text-right font-mono text-xs text-fg-2 tabular-nums">
              {{ formatGovernNumber(rows.reduce((sum, row) => sum + row.requests, 0)) }}
            </td>
            <td colspan="3" class="text-right text-[0.625rem] leading-4 text-fg-3">
              {{ reconcilesWithin ? "Adds back to the usage tab's window total." : "Does not add back to the window total." }}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>

    <p class="text-[0.6875rem] leading-4 text-fg-3">{{ summary }}</p>

    <section class="rounded-lg border border-line-subtle bg-surface-1 p-3" aria-label="Biggest movement">
      <h2 class="text-xs font-medium text-fg-1">Biggest movement in the window</h2>
      <p class="mt-0.5 text-[0.625rem] leading-4 text-fg-3">
        Ranked by absolute change; the sign tells you which way. Rows with no prior window are excluded rather than counted
        as flat.
      </p>
      <ul class="mt-2 flex flex-col gap-1.5">
        <li v-for="row in movers" :key="`mover-${row.id}`" class="flex flex-wrap items-baseline gap-x-2 text-xs">
          <span class="font-mono text-sm leading-5 font-semibold tabular-nums" :class="deltaClass(row.deltaPercent)">
            {{ deltaText(row) }}
          </span>
          <span class="text-fg-1">{{ row.name }}</span>
          <span class="text-[0.625rem] text-fg-3">
            {{ formatGovernPercent(row.spendSharePercent, 1) }} of spend · {{ formatMetric("spendUsd", row.spendUsd) }}
          </span>
        </li>
        <li v-if="movers.length === 0" class="text-xs text-fg-3">No row in this split has a comparable prior window.</li>
      </ul>
    </section>

    <GovernCaveat
      v-if="unattributed.length > 0"
      tone="warning"
      :title="`Unattributed ${DIMENSION_LABELS[dimension].toLowerCase()} volume keeps its own row`"
    >
      {{ formatGovernPercent(unattributed.reduce((sum, row) => sum + row.spendSharePercent, 0), 1) }} of window spend has no
      {{ DIMENSION_LABELS[dimension].toLowerCase() }} attached. It is not dropped, and it is not spread across the named rows;
      doing either would make the named shares look more certain than they are. Attribution is written by the relay, so a
      missing value means the relay never recorded one.
    </GovernCaveat>

    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-fg-3">
      <NuxtLink
        to="/budgets"
        class="inline-flex items-center gap-1 text-fg-2 underline decoration-line-strong underline-offset-2 hover:text-fg-1"
      >
        Spend limits by scope
      </NuxtLink>
      <span>
        Window: {{ points.length }} recorded days, {{ formatMetric("requests", metricTotal(points, "requests")) }} requests,
        {{ formatMetric("spendUsd", windowSpend) }}
      </span>
    </div>

    <GovernPendingData
      title="Certified cost by dimension"
      :contract="ANALYTICS_USAGE_CONTRACT"
      description="A dimension split becomes evidence only when it is produced from certified usage rows. Until then this table answers 'where did the volume go', never 'what should this tenant be billed for'."
    />
  </div>
</template>
