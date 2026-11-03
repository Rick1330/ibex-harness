<script setup lang="ts">
import { seriesColor } from '~/utils/series'

export interface BenchmarkSeries {
  label: string
  values: number[]
  color?: string
  suffix?: string
  digits?: number
  dashed?: boolean
}

const props = withDefaults(defineProps<{
  series: BenchmarkSeries[]
  labels?: string[]
  width?: number
  height?: number
  threshold?: number
  thresholdLabel?: string
  showLegend?: boolean
  minimal?: boolean
  filled?: boolean
  yTicks?: number
  maxXLabels?: number
  compact?: boolean
  activeIndex?: number | null
}>(), {
  labels: () => [],
  width: 720,
  height: 190,
  threshold: undefined,
  thresholdLabel: '',
  showLegend: false,
  minimal: false,
  filled: true,
  yTicks: 4,
  maxXLabels: 6,
  compact: false,
  activeIndex: null,
})

const uid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
const width = props.width

const padding = computed(() => {
  if (props.minimal) return { top: 5, right: 5, bottom: 5, left: 5 }
  if (props.compact) return { top: 18, right: 12, bottom: 30, left: 74 }
  return { top: 16, right: 12, bottom: 26, left: 42 }
})

const cleanSeries = computed(() => props.series.map((series, index) => ({
  ...series,
  color: series.color ?? seriesColor(index),
  digits: series.digits ?? 2,
  suffix: series.suffix ?? '',
  values: series.values.filter(value => Number.isFinite(value)),
})).filter(series => series.values.length > 0))

const bounds = computed(() => {
  const values = cleanSeries.value.flatMap(series => series.values)
  if (!values.length) return { min: 0, max: 1 }

  const scale = props.threshold === undefined ? values : [...values, props.threshold]
  let min = Math.min(...scale)
  let max = Math.max(...scale)
  if (min === max) {
    min = Math.max(0, min - 1)
    max = max + 1
  }

  const span = max - min
  return {
    min: Math.max(0, min - span * 0.16),
    max: max + span * 0.16,
  }
})

const innerWidth = computed(() => width - padding.value.left - padding.value.right)
const innerHeight = computed(() => props.height - padding.value.top - padding.value.bottom)

function xFor(index: number, length: number) {
  if (length === 1) return padding.value.left + innerWidth.value / 2
  return padding.value.left + (index / (length - 1)) * innerWidth.value
}

function yFor(value: number) {
  return padding.value.top + innerHeight.value - ((value - bounds.value.min) / (bounds.value.max - bounds.value.min)) * innerHeight.value
}

const plottedSeries = computed(() => cleanSeries.value.map(series => ({
  ...series,
  points: series.values.map((value, index) => ({
    x: xFor(index, series.values.length),
    y: yFor(value),
    value,
  })),
})))

function linePath(points: { x: number, y: number }[]) {
  if (!points.length) return ''
  if (points.length === 1) return `M${points[0]!.x.toFixed(2)},${points[0]!.y.toFixed(2)}`

  let path = `M${points[0]!.x.toFixed(2)},${points[0]!.y.toFixed(2)}`
  for (let index = 0; index < points.length - 1; index += 1) {
    const previous = points[index - 1] ?? points[index]!
    const current = points[index]!
    const next = points[index + 1]!
    const after = points[index + 2] ?? next
    const controlOneX = current.x + (next.x - previous.x) / 6
    const controlOneY = current.y + (next.y - previous.y) / 6
    const controlTwoX = next.x - (after.x - current.x) / 6
    const controlTwoY = next.y - (after.y - current.y) / 6
    path += ` C${controlOneX.toFixed(2)},${controlOneY.toFixed(2)} ${controlTwoX.toFixed(2)},${controlTwoY.toFixed(2)} ${next.x.toFixed(2)},${next.y.toFixed(2)}`
  }
  return path
}

function areaPath(points: { x: number, y: number }[]) {
  if (points.length < 2) return ''
  const first = points[0]!
  const last = points[points.length - 1]!
  const baseline = props.height - padding.value.bottom
  return `${linePath(points)} L${last.x.toFixed(2)},${baseline} L${first.x.toFixed(2)},${baseline} Z`
}

const ticks = computed(() => Array.from({ length: props.yTicks }, (_, index) => {
  const ratio = props.yTicks === 1 ? 0 : index / (props.yTicks - 1)
  return {
    y: padding.value.top + ratio * innerHeight.value,
    value: bounds.value.max - ratio * (bounds.value.max - bounds.value.min),
  }
}))

const labelStep = computed(() => Math.max(1, Math.ceil((props.labels?.length || 1) / props.maxXLabels)))
const thresholdY = computed(() => {
  if (props.threshold === undefined) return null
  return yFor(props.threshold)
})

const active = computed(() => {
  if (props.activeIndex === null || props.activeIndex === undefined) return null
  const length = plottedSeries.value[0]?.values.length ?? 0
  if (!length) return null
  const index = Math.max(0, Math.min(length - 1, props.activeIndex))
  return {
    x: xFor(index, length),
    points: plottedSeries.value
      .filter(line => line.points[index])
      .map(line => ({ ...line.points[index]!, color: line.color })),
  }
})

function formatValue(value: number, digits: number, suffix: string) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value) + suffix
}

function axisValue(value: number) {
  const series = cleanSeries.value[0]
  if (props.compact) {
    const digits = Math.min(series?.digits ?? 2, 2)
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
  }
  return formatValue(value, series?.digits ?? 2, series?.suffix ?? '')
}

function fillUrl(index: number) {
  return `url(#${uid}-fill-${index})`
}
</script>

<template>
  <div v-if="plottedSeries.length" class="w-full">
    <svg
      class="site-chart h-auto w-full overflow-visible"
      :class="props.compact ? 'site-chart--compact' : ''"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="`Benchmark chart: ${plottedSeries.map(series => `${series.label} ${series.values.join(', ')}`).join('; ')}`"
    >
      <defs>
        <linearGradient
          v-for="(line, seriesIndex) in plottedSeries"
          :id="`${uid}-fill-${seriesIndex}`"
          :key="`fill-${line.label}`"
          x1="0"
          y1="0"
          x2="0"
          y2="1"
        >
          <stop offset="0%" :stop-color="line.color" stop-opacity="0.26" />
          <stop offset="62%" :stop-color="line.color" stop-opacity="0.08" />
          <stop offset="100%" :stop-color="line.color" stop-opacity="0" />
        </linearGradient>
      </defs>

      <g v-if="!minimal">
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
          :key="`label-${tick.y}`"
          :x="padding.left - 9"
          :y="tick.y + 3.5"
          text-anchor="end"
        >{{ axisValue(tick.value) }}</text>
      </g>

      <g v-if="thresholdY !== null">
        <line class="threshold" :x1="padding.left" :x2="width - padding.right" :y1="thresholdY" :y2="thresholdY" />
        <text v-if="!minimal" class="threshold-label" :x="width - padding.right" :y="thresholdY - 7" text-anchor="end">{{ thresholdLabel }}</text>
      </g>

      <g v-if="active">
        <line class="active-guide" :x1="active.x" :x2="active.x" :y1="padding.top" :y2="height - padding.bottom" />
        <circle
          v-for="point in active.points"
          :key="`active-${point.color}`"
          class="active-point"
          :cx="point.x"
          :cy="point.y"
          r="4.5"
          :fill="point.color"
        />
      </g>

      <g v-for="(line, seriesIndex) in plottedSeries" :key="line.label">
        <path
          v-if="filled && seriesIndex === 0 && line.points.length > 1"
          class="series-fill"
          :d="areaPath(line.points)"
          :fill="fillUrl(seriesIndex)"
        />
        <path
          class="series"
          :d="linePath(line.points)"
          :stroke="line.color"
          :stroke-dasharray="line.dashed ? '4 5' : undefined"
          :style="{ '--series-color': line.color }"
        />
        <circle
          v-for="(point, pointIndex) in line.points"
          v-show="line.points.length <= 12"
          :key="pointIndex"
          :cx="point.x"
          :cy="point.y"
          r="3.2"
          :fill="line.color"
          stroke="var(--site-bg)"
          stroke-width="2"
        />
      </g>

      <template v-if="!minimal">
        <text
          v-for="(label, index) in labels"
          v-show="index % labelStep === 0 || index === labels.length - 1"
          :key="`x-${index}`"
          :x="xFor(index, labels.length)"
          :y="height - 7"
          :text-anchor="labels.length === 1 ? 'middle' : index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'"
        >{{ label }}</text>
      </template>
    </svg>

    <div v-if="showLegend" class="mt-4 grid gap-2">
      <div
        v-for="entry in plottedSeries"
        :key="`legend-${entry.label}`"
        class="flex items-center gap-2 text-xs"
      >
        <span class="size-1.5 shrink-0 rounded-full" :style="{ background: entry.color }" />
        <span class="text-[var(--site-muted)]">{{ entry.label }}</span>
        <span class="ml-auto font-mono tabular-nums text-[var(--site-ink)]">
          {{ formatValue(entry.values[entry.values.length - 1]!, entry.digits, entry.suffix) }}
        </span>
        <span class="font-mono text-[0.5rem] uppercase tracking-[0.1em] text-[var(--site-muted)]">latest</span>
      </div>
    </div>
  </div>
</template>
