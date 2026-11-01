<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    values: number[]
    labels: string[]
    label: string
    color?: string
    height?: number
  }>(),
  { color: "var(--ix-s1)", height: 120 },
)

const width = 520
const padding = { top: 8, right: 4, bottom: 18, left: 4 }

const geometry = computed(() => {
  const values = props.values
  if (!values.length) return null
  const max = Math.max(1, ...values)
  const innerW = width - padding.left - padding.right
  const innerH = props.height - padding.top - padding.bottom
  const step = innerW / values.length
  const barW = Math.max(2, Math.min(18, step * 0.52))
  return {
    max,
    bars: values.map((value, index) => {
      const h = Math.max(1, (value / max) * innerH)
      return {
        x: padding.left + index * step + (step - barW) / 2,
        y: padding.top + innerH - h,
        width: barW,
        height: h,
        value,
        label: props.labels[index] ?? "",
      }
    }),
    baseline: padding.top + innerH,
  }
})
</script>

<template>
  <div class="min-w-0">
    <svg
      v-if="geometry"
      :viewBox="`0 0 ${width} ${height}`"
      class="h-auto w-full"
      role="img"
      :aria-label="`${label}. ${values.length} points, maximum ${geometry.max}.`"
    >
      <g aria-hidden="true">
        <line
          v-for="tick in [0, 1, 2, 3]"
          :key="tick"
          :x1="padding.left"
          :x2="width - padding.right"
          :y1="padding.top + ((geometry.baseline - padding.top) * tick) / 3"
          :y2="padding.top + ((geometry.baseline - padding.top) * tick) / 3"
          stroke="var(--ix-line-subtle)"
          stroke-width="1"
          stroke-dasharray="2 4"
        />
      </g>
      <line
        :x1="padding.left"
        :x2="width - padding.right"
        :y1="geometry.baseline"
        :y2="geometry.baseline"
        stroke="var(--ix-line)"
        stroke-width="1"
      />
      <rect
        v-for="(bar, index) in geometry.bars"
        :key="index"
        :x="bar.x"
        :y="bar.y"
        :width="bar.width"
        :height="bar.height"
        :fill="color"
        rx="1"
        opacity="0.9"
      >
        <title>{{ bar.label }}: {{ bar.value }}</title>
      </rect>
    </svg>
    <div class="mt-1 flex justify-between font-mono text-[0.625rem] text-fg-3">
      <span>{{ labels[0] }}</span>
      <span v-if="labels.length > 2">{{ labels[Math.floor(labels.length / 2)] }}</span>
      <span>{{ labels.at(-1) }}</span>
    </div>
  </div>
</template>
