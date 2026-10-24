<script setup lang="ts">
import { seriesColor } from '~/utils/series'

export interface BarSeries {
  label: string
  values: number[]
  color?: string
  suffix?: string
  digits?: number
}

const props = withDefaults(defineProps<{
  labels: string[]
  series: BarSeries[]
  width?: number
  height?: number
  threshold?: number
  thresholdLabel?: string
  showLegend?: boolean
  showValues?: boolean
  yTicks?: number
  compact?: boolean
}>(), {
  width: 720,
  height: 220,
  threshold: undefined,
  thresholdLabel: '',
  showLegend: true,
  showValues: false,
  yTicks: 4,
  compact: false,
})

const width = props.width
const padding = computed(() => (props.compact
  ? { top: 20, right: 10, bottom: 34, left: 74 }
  : { top: 18, right: 10, bottom: 32, left: 44 }))

const cleanSeries = computed(() => props.series.map((entry, index) => ({
  ...entry,
  color: entry.color ?? seriesColor(index),
  suffix: entry.suffix ?? '',
  digits: entry.digits ?? 1,
})))

const count = computed(() => Math.max(1, props.labels.length))
const innerWidth = computed(() => width - padding.value.left - padding.value.right)
const innerHeight = computed(() => props.height - padding.value.top - padding.value.bottom)

function stepFraction(fraction: number): number {
  if (fraction <= 1) return 1
  if (fraction <= 2) return 2
  if (fraction <= 2.5) return 2.5
  if (fraction <= 5) return 5
  return 10
}

const ceiling = computed(() => {
  const values = cleanSeries.value.flatMap(entry => entry.values)
  if (props.threshold !== undefined) values.push(props.threshold)
  const largest = Math.max(...values, 0.001)
  const roughStep = largest / props.yTicks
  const magnitude = 10 ** Math.floor(Math.log10(roughStep))
  const fraction = roughStep / magnitude
  const step = stepFraction(fraction) * magnitude
  return Math.ceil(largest / step) * step
})

const groupWidth = computed(() => innerWidth.value / count.value)
const groupGap = computed(() => groupWidth.value * 0.24)
const barWidth = computed(() => Math.max(4, (groupWidth.value - groupGap.value) / cleanSeries.value.length - 5))

const baseline = computed(() => padding.value.top + innerHeight.value)

function barX(groupIndex: number, seriesIndex: number) {
  return padding.value.left + groupIndex * groupWidth.value + groupGap.value / 2 + seriesIndex * (barWidth.value + 5)
}

function yFor(value: number) {
  const ratio = Math.min(1, Math.max(0, value / ceiling.value))
  return baseline.value - ratio * innerHeight.value
}

function barHeight(value: number) {
  return Math.max(2, baseline.value - yFor(value))
}

const ticks = computed(() => Array.from({ length: props.yTicks }, (_, index) => {
  const ratio = index / (props.yTicks - 1)
  return {
    y: padding.value.top + ratio * innerHeight.value,
    value: ceiling.value - ratio * ceiling.value,
  }
}))

const thresholdY = computed(() => props.threshold === undefined ? null : yFor(props.threshold))

function formatValue(value: number, series: BarSeries) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: series.digits ?? 1 }).format(value) + series.suffix
}

function tickValue(value: number) {
  const series = cleanSeries.value[0]
  if (props.compact) {
    const digits = Math.min(series?.digits ?? 1, 1)
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
  }
  return series ? formatValue(value, series) : String(value)
}
</script>

<template>
  <div class="w-full">
    <svg
      class="site-chart site-bars h-auto w-full overflow-visible"
      :class="props.compact ? 'site-chart--compact' : ''"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="`Grouped bar chart: ${labels.map((label, index) => `${label} ${cleanSeries.map(entry => `${entry.label} ${entry.values[index] ?? 0}`).join(', ')}`).join('; ')}`"
    >
      <g>
        <line
          v-for="tick in ticks"
          :key="`grid-${tick.y}`"
          class="grid"
          :x1="padding.left"
          :x2="width - padding.right"
          :y1="tick.y"
          :y2="tick.y"
        />
        <text
          v-for="tick in ticks"
          :key="`tick-${tick.y}`"
          :x="padding.left - 9"
          :y="tick.y + 3.5"
          text-anchor="end"
        >{{ tickValue(tick.value) }}</text>
      </g>

      <g v-if="thresholdY !== null">
        <line class="threshold" :x1="padding.left" :x2="width - padding.right" :y1="thresholdY" :y2="thresholdY" />
        <text class="threshold-label" :x="width - padding.right" :y="thresholdY - 7" text-anchor="end">{{ thresholdLabel }}</text>
      </g>

      <g v-for="(label, groupIndex) in labels" :key="label">
        <rect
          v-for="(entry, seriesIndex) in cleanSeries"
          :key="`${label}-${entry.label}`"
          :x="barX(groupIndex, seriesIndex)"
          :y="yFor(entry.values[groupIndex] ?? 0)"
          :width="barWidth"
          :height="barHeight(entry.values[groupIndex] ?? 0)"
          :fill="entry.color"
          rx="3"
        />
        <template v-if="showValues">
          <text
            v-for="(entry, seriesIndex) in cleanSeries"
            :key="`${label}-${entry.label}-value`"
            :x="barX(groupIndex, seriesIndex) + barWidth / 2"
            :y="yFor(entry.values[groupIndex] ?? 0) - 5"
            text-anchor="middle"
          >{{ formatValue(entry.values[groupIndex] ?? 0, entry) }}</text>
        </template>
        <text
          :x="padding.left + groupIndex * groupWidth + groupWidth / 2"
          :y="height - 8"
          text-anchor="middle"
        >{{ label }}</text>
      </g>
    </svg>

    <div v-if="showLegend" class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
      <span v-for="entry in cleanSeries" :key="`legend-${entry.label}`" class="flex items-center gap-2 text-xs">
        <span class="size-1.5 rounded-full" :style="{ background: entry.color }" />
        <span class="text-[var(--site-muted)]">{{ entry.label }}</span>
        <span class="font-mono tabular-nums text-[var(--site-ink)]">{{ formatValue(entry.values[entry.values.length - 1] ?? 0, entry) }}</span>
      </span>
    </div>
  </div>
</template>
