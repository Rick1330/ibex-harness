<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    points: number[]
    label: string
    width?: number
    height?: number
    band?: { low: number; high: number } | null
    /** Marks the whole chart as illustrative: adds a stripe overlay. */
    illustrative?: boolean
  }>(),
  { width: 80, height: 24, band: null, illustrative: false },
)

const geometry = computed(() => {
  const values = props.points
  if (values.length === 0) return { line: "", band: null, last: null }
  const candidates = [...values]
  if (props.band) candidates.push(props.band.low, props.band.high)
  let min = Math.min(...candidates)
  let max = Math.max(...candidates)
  if (min === max) {
    min -= 1
    max += 1
  }
  const pad = (max - min) * 0.12
  min -= pad
  max += pad
  const innerW = props.width - 2
  const innerH = props.height - 3
  const step = values.length > 1 ? innerW / (values.length - 1) : innerW
  const y = (value: number) => Math.round((props.height - 1.5 - ((value - min) / (max - min)) * innerH) * 100) / 100
  const coords = values.map((value, index) => ({
    x: Math.round((1 + index * step) * 100) / 100,
    y: y(value),
  }))
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ")
  const band = props.band
    ? (() => {
        const top = y(props.band.high)
        const bottom = y(props.band.low)
        return { y: top, height: Math.max(1, bottom - top) }
      })()
    : null
  return { line, band, last: coords.at(-1) ?? null }
})

const outOfBand = computed(() => {
  if (!props.band || props.points.length === 0) return false
  const last = props.points.at(-1)!
  return last > props.band.high || last < props.band.low
})

const stroke = computed(() => (outOfBand.value ? "var(--ix-crit)" : "var(--ix-s1)"))
</script>

<template>
  <svg
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    fill="none"
    class="shrink-0 overflow-visible"
    role="img"
    :aria-label="illustrative ? `${label}. Illustrative data.` : label"
  >
    <rect
      v-if="geometry.band"
      x="0"
      :y="geometry.band.y"
      :width="width"
      :height="geometry.band.height"
      fill="var(--ix-line-strong)"
      opacity="0.12"
    />
    <path v-if="geometry.line" :d="geometry.line" :stroke="stroke" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" />
    <circle v-if="geometry.last" :cx="geometry.last.x" :cy="geometry.last.y" r="1.75" :fill="stroke" />
  </svg>
</template>
