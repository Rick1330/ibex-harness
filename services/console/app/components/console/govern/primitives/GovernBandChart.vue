<script setup lang="ts">
import { computed, ref } from "vue"
import { ChevronDown, Table2 } from "@lucide/vue"
import { formatGovernShortDate } from "@/lib/govern-format"
import type { DriftMarker, DriftPoint } from "@/lib/drift-preview"

const props = withDefaults(
  defineProps<{
    points: DriftPoint[]
    threshold: number
    unit: string
    label: string
    markers?: DriftMarker[]
    summary?: string | null
    illustrative?: boolean
  }>(),
  { markers: () => [], summary: null, illustrative: false },
)

const VIEW_W = 820
const VIEW_H = 320
const PAD = { left: 52, right: 20, top: 24, bottom: 36 }

const showTable = ref(false)

interface Geometry {
  band: string
  observedSegments: { d: string; out: boolean }[]
  outRegions: { x: number; width: number }[]
  thresholdY: number
  baselineY: number
  yTicks: { y: number; value: number }[]
  xTicks: { x: number; label: string }[]
  markerTs: { x: number; label: string }[]
  last: { x: number; y: number } | null
}

const geometry = computed<Geometry>(() => {
  const points = props.points
  const empty: Geometry = {
    band: "",
    observedSegments: [],
    outRegions: [],
    thresholdY: 0,
    baselineY: 0,
    yTicks: [],
    xTicks: [],
    markerTs: [],
    last: null,
  }
  if (points.length === 0) return empty

  const values: number[] = [props.threshold]
  for (const point of points) values.push(point.observed, point.baseline, point.low, point.high)
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = (max - min) * 0.12
  min -= pad
  max += pad

  const plotW = VIEW_W - PAD.left - PAD.right
  const plotH = VIEW_H - PAD.top - PAD.bottom
  const step = points.length > 1 ? plotW / (points.length - 1) : plotW
  const xAt = (index: number) => PAD.left + index * step
  const yAt = (value: number) => PAD.top + plotH - ((value - min) / (max - min)) * plotH

  const bandTop = points.map((point, index) => `${xAt(index)},${yAt(point.high)}`)
  const bandBottom = [...points].reverse().map((point, index) => `${xAt(points.length - 1 - index)},${yAt(point.low)}`)
  const band = [...bandTop, ...bandBottom].join(" ")

  const segments: { d: string; out: boolean }[] = []
  const regions: { x: number; width: number }[] = []
  let runStart: number | null = null
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index]!
    const out = point.observed > point.high || point.observed < point.low
    if (index > 0) {
      const prev = points[index - 1]!
      const prevOut = prev.observed > prev.high || prev.observed < prev.low
      segments.push({
        d: `M${xAt(index - 1)},${yAt(prev.observed)} L${xAt(index)},${yAt(point.observed)}`,
        out: out || prevOut,
      })
    }
    if (out && runStart === null) runStart = index
    if (!out && runStart !== null) {
      regions.push({
        x: xAt(runStart) - step / 2,
        width: Math.max(step, xAt(index - 1) - xAt(runStart)),
      })
      runStart = null
    }
  }
  if (runStart !== null) {
    regions.push({ x: xAt(runStart) - step / 2, width: Math.max(step, xAt(points.length - 1) - xAt(runStart)) })
  }

  const ticks = [min + pad, (min + max) / 2, max - pad].map((value) => ({ y: yAt(value), value }))
  const tickIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])]
  const xTicks = tickIndexes.map((index) => ({ x: xAt(index), label: formatGovernShortDate(points[index]!.date) }))

  const firstTime = Date.parse(points[0]!.date)
  const lastTime = Date.parse(points.at(-1)!.date)
  const markerTs = props.markers
    .map((marker) => {
      const time = Date.parse(marker.at)
      if (!Number.isFinite(time) || lastTime === firstTime) return null
      const ratio = (time - firstTime) / (lastTime - firstTime)
      if (ratio < 0 || ratio > 1) return null
      return { x: PAD.left + ratio * plotW, label: marker.label }
    })
    .filter((entry): entry is { x: number; label: string } => Boolean(entry))

  return {
    band,
    observedSegments: segments,
    outRegions: regions,
    thresholdY: yAt(props.threshold),
    baselineY: yAt(points[0]!.baseline),
    yTicks: ticks,
    xTicks,
    markerTs,
    last: { x: xAt(points.length - 1), y: yAt(points.at(-1)!.observed) },
  }
})

const axisDigits = computed(() => (props.unit === "share" ? 1 : 2))

function axisValue(value: number): string {
  if (props.unit === "share") return `${Math.round(value * 100)}%`
  return value.toFixed(axisDigits.value)
}

function cellValue(value: number): string {
  if (props.unit === "share") return `${Math.round(value * 100)}%`
  return value.toFixed(2)
}
</script>

<template>
  <figure class="min-w-0">
    <div class="relative overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <svg
        :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`"
        class="h-auto w-full"
        role="img"
        :aria-label="`${label}${illustrative ? '. Illustrative data.' : ''}`"
      >
        <g v-for="region in geometry.outRegions" :key="`region-${region.x}`">
          <rect :x="region.x" :y="PAD.top" :width="region.width" :height="VIEW_H - PAD.top - PAD.bottom" fill="var(--ix-crit)" opacity="0.06" />
        </g>
        <line
          v-for="tick in geometry.yTicks"
          :key="`grid-${tick.y}`"
          :x1="PAD.left"
          :x2="VIEW_W - PAD.right"
          :y1="tick.y"
          :y2="tick.y"
          stroke="var(--ix-line-subtle)"
          stroke-width="1"
        />
        <text
          v-for="tick in geometry.yTicks"
          :key="`ytick-${tick.y}`"
          :x="PAD.left - 8"
          :y="tick.y + 3.5"
          text-anchor="end"
          font-size="10"
          fill="var(--ix-fg-3)"
          font-family="var(--font-mono)"
        >{{ axisValue(tick.value) }}</text>

        <polygon v-if="geometry.band" :points="geometry.band" fill="var(--ix-s1)" opacity="0.08" />
        <line
          :x1="PAD.left"
          :x2="VIEW_W - PAD.right"
          :y1="geometry.baselineY"
          :y2="geometry.baselineY"
          stroke="var(--ix-line-strong)"
          stroke-width="1"
          stroke-dasharray="2 3"
          opacity="0.7"
        />
        <line
          :x1="PAD.left"
          :x2="VIEW_W - PAD.right"
          :y1="geometry.thresholdY"
          :y2="geometry.thresholdY"
          stroke="var(--ix-warn)"
          stroke-width="1.25"
          stroke-dasharray="5 4"
        />
        <text
          :x="VIEW_W - PAD.right"
          :y="geometry.thresholdY - 5"
          text-anchor="end"
          font-size="10"
          fill="var(--ix-warn)"
          font-family="var(--font-mono)"
        >threshold {{ axisValue(threshold) }}</text>

        <path
          v-for="(segment, index) in geometry.observedSegments"
          :key="`seg-${index}`"
          :d="segment.d"
          :stroke="segment.out ? 'var(--ix-crit)' : 'var(--ix-s1)'"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle v-if="geometry.last" :cx="geometry.last.x" :cy="geometry.last.y" r="3" fill="var(--ix-s1)" />

        <g v-for="(marker, index) in geometry.markerTs" :key="`marker-${index}`">
          <line
            :x1="marker.x"
            :x2="marker.x"
            :y1="PAD.top"
            :y2="VIEW_H - PAD.bottom"
            stroke="var(--ix-accent)"
            stroke-width="1"
            stroke-dasharray="2 4"
            opacity="0.55"
          />
          <circle :cx="marker.x" :cy="PAD.top" r="3.5" fill="var(--ix-accent)">
            <title>{{ marker.label }}</title>
          </circle>
        </g>

        <text
          v-for="tick in geometry.xTicks"
          :key="`xtick-${tick.x}`"
          :x="tick.x"
          :y="VIEW_H - 12"
          :text-anchor="tick.x <= PAD.left ? 'start' : tick.x >= VIEW_W - PAD.right ? 'end' : 'middle'"
          font-size="10"
          fill="var(--ix-fg-3)"
          font-family="var(--font-mono)"
        >{{ tick.label }}</text>
      </svg>
    </div>

    <figcaption class="mt-2 flex flex-wrap items-start justify-between gap-2">
      <p v-if="summary" class="min-w-0 flex-1 text-xs leading-5 text-fg-2 text-pretty">{{ summary }}</p>
      <button
        type="button"
        class="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-line-subtle bg-surface-1 px-2 text-[0.6875rem] text-fg-3 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :aria-expanded="showTable"
        @click="showTable = !showTable"
      >
        <Table2 :size="12" :stroke-width="1.9" aria-hidden="true" />
        View as table
        <ChevronDown :size="11" :stroke-width="2" :class="showTable && 'rotate-180'" class="transition-transform" aria-hidden="true" />
      </button>
    </figcaption>

    <div v-if="showTable" class="ix-scroll mt-2 max-h-64 overflow-auto rounded-lg border border-line-subtle">
      <table class="ix-agent-table" :aria-label="`${label} values`">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Observed</th>
            <th scope="col">Baseline</th>
            <th scope="col">Band</th>
            <th scope="col">Threshold</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in points" :key="point.date">
            <td class="font-mono text-[0.6875rem]">{{ formatGovernShortDate(point.date) }}</td>
            <td class="font-mono text-[0.6875rem]">{{ cellValue(point.observed) }}</td>
            <td class="font-mono text-[0.6875rem]">{{ cellValue(point.baseline) }}</td>
            <td class="font-mono text-[0.6875rem]">{{ cellValue(point.low) }} – {{ cellValue(point.high) }}</td>
            <td class="font-mono text-[0.6875rem]">{{ cellValue(threshold) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </figure>
</template>
