<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{
  values: number[]
  labels: string[]
  label: string
  format: (value: number) => string
  height?: number
  color?: string
}>()

const WIDTH = 660
const chartColor = computed(() => props.color ?? "var(--ix-s1)")
const PAD = { top: 12, right: 12, bottom: 22, left: 52 }

const geometry = computed(() => {
  const values = props.values
  if (values.length < 2) return null
  const height = props.height ?? 200
  const innerW = WIDTH - PAD.left - PAD.right
  const innerH = height - PAD.top - PAD.bottom
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin || rawMax || 1
  const min = Math.max(0, rawMin - span * 0.18)
  const max = rawMax + span * 0.12
  const x = (index: number) => PAD.left + (index / (values.length - 1)) * innerW
  const y = (value: number) => PAD.top + innerH - ((value - min) / (max - min)) * innerH
  const coords = values.map((value, index) => ({ x: x(index), y: y(value), value }))
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ")
  const area = `${line} L${coords.at(-1)!.x.toFixed(1)},${(PAD.top + innerH).toFixed(1)} L${coords[0]!.x.toFixed(1)},${(PAD.top + innerH).toFixed(1)} Z`
  const ticks = [min, min + (max - min) / 2, max].map((value) => ({ value, y: y(value) }))
  return { height, innerH, coords, line, area, ticks, baseline: PAD.top + innerH }
})

const xLabels = computed(() => {
  const labels = props.labels
  if (labels.length === 0) return []
  const picks = [...new Set([0, Math.floor((labels.length - 1) / 2), labels.length - 1])]
  const lastIndex = labels.length - 1
  return picks.map((index) => ({
    index,
    label: labels[index] ?? "",
    anchor: index === 0 ? "start" : index === lastIndex ? "end" : "middle",
  }))
})
</script>

<template>
  <div v-if="!geometry" class="rounded-lg border border-line-subtle bg-surface-1 px-3 py-6 text-center text-xs text-fg-3">
    Fewer than two recorded days. A trend needs at least two points, so none is drawn.
  </div>

  <figure v-else class="flex flex-col gap-1.5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <figcaption class="text-xs font-medium text-fg-1">{{ label }}</figcaption>
    </div>

    <svg
      :viewBox="`0 0 ${WIDTH} ${geometry.height}`"
      :height="geometry.height"
      class="w-full"
      fill="none"
      role="img"
      :aria-label="`${label}. Illustrative fixture series across ${values.length} recorded days. Turn on the day-by-day values to read the exact numbers.`"
    >
      <defs>
        <linearGradient id="ix-chart-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="chartColor" stop-opacity="0.22" />
          <stop offset="100%" :stop-color="chartColor" stop-opacity="0" />
        </linearGradient>
      </defs>

      <g aria-hidden="true">
        <line
          v-for="tick in geometry.ticks"
          :key="`grid-${tick.value}`"
          :x1="PAD.left"
          :x2="WIDTH - PAD.right"
          :y1="tick.y"
          :y2="tick.y"
          stroke="var(--ix-line-subtle)"
          stroke-width="1"
        />
        <text
          v-for="tick in geometry.ticks"
          :key="`tick-${tick.value}`"
          :x="PAD.left - 8"
          :y="tick.y + 3.5"
          text-anchor="end"
          class="fill-fg-3 font-mono"
          font-size="10"
        >
          {{ format(tick.value) }}
        </text>
      </g>

      <path :d="geometry.area" fill="url(#ix-chart-fill)" />
      <path :d="geometry.line" :stroke="chartColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />

      <circle :cx="geometry.coords.at(-1)?.x" :cy="geometry.coords.at(-1)?.y" r="3" :fill="chartColor" />

      <g aria-hidden="true">
        <text
          v-for="tick in xLabels"
          :key="`x-${tick.index}`"
          :x="geometry.coords[tick.index]?.x"
          :y="geometry.height - 6"
          :text-anchor="tick.anchor"
          class="fill-fg-3 font-mono"
          font-size="10"
        >
          {{ tick.label }}
        </text>
      </g>
    </svg>
  </figure>
</template>
