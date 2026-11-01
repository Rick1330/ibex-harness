<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    points: Array<{ date: string; count: number }>
    label: string
    width?: number
    height?: number
  }>(),
  { width: 48, height: 18 },
)

const geometry = computed(() => {
  const points = props.points
  if (points.length === 0) return { line: "", area: "" }
  const max = Math.max(1, ...points.map((point) => point.count))
  const step = points.length > 1 ? props.width / (points.length - 1) : props.width
  const coords = points.map((point, index) => {
    const x = Math.round(index * step * 100) / 100
    const y = Math.round((props.height - 2 - (point.count / max) * (props.height - 5)) * 100) / 100
    return { x, y }
  })
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ")
  const area = `${line} L${props.width},${props.height} L0,${props.height} Z`
  return { line, area }
})
</script>

<template>
  <svg
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    fill="none"
    class="shrink-0 overflow-visible"
    role="img"
    :aria-label="label"
  >
    <path v-if="geometry.area" :d="geometry.area" fill="color-mix(in srgb, var(--ix-s1) 14%, transparent)" />
    <path
      v-if="geometry.line"
      :d="geometry.line"
      stroke="var(--ix-s1)"
      stroke-width="1.25"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
