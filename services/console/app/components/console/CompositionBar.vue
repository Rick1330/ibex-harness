<script setup lang="ts">
import { computed } from "vue"

type Segment = {
  label: string
  value: number
  color: string
}

const props = withDefaults(
  defineProps<{
    title: string
    segments: Segment[]
    height?: "sm" | "md"
    showTotal?: boolean
  }>(),
  { height: "sm", showTotal: true },
)

const total = computed(() => props.segments.reduce((sum, segment) => sum + segment.value, 0))
const visible = computed(() => props.segments.filter((segment) => segment.value > 0))
</script>

<template>
  <section class="min-w-0">
    <div class="flex items-baseline justify-between gap-2">
      <h3 class="text-[0.6875rem] font-medium text-fg-3">{{ title }}</h3>
      <span v-if="showTotal" class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ total }}</span>
    </div>
    <div
      class="mt-2 flex w-full overflow-hidden rounded-full bg-raised"
      :class="height === 'sm' ? 'h-1.5' : 'h-2.5'"
      role="img"
      :aria-label="`${title}: ${visible.map((segment) => `${segment.label} ${segment.value}`).join(', ')}`"
    >
      <span
        v-for="segment in visible"
        :key="segment.label"
        :style="{ width: `${(segment.value / Math.max(total, 1)) * 100}%` }"
        :class="segment.color"
      />
    </div>
    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-fg-3">
      <span v-for="segment in segments" :key="segment.label" class="inline-flex items-center gap-1.5">
        <span class="size-1.5 rounded-full" :class="segment.color" aria-hidden="true" />
        {{ segment.label }}
        <span class="font-mono tabular-nums text-fg-2">{{ segment.value }}</span>
      </span>
    </div>
  </section>
</template>
