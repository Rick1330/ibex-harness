<script setup lang="ts">
import { computed } from "vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"

const props = withDefaults(
  defineProps<{
    value: number
    limit: number
    valueLabel: string
    limitLabel: string
    /** Optional threshold tick as an absolute value on the same scale. */
    threshold?: number | null
    thresholdLabel?: string
    label: string
  }>(),
  { threshold: null, thresholdLabel: undefined },
)

const ratio = computed(() => (props.limit > 0 ? Math.min(1, Math.max(0, props.value / props.limit)) : 0))
const tick = computed(() =>
  props.threshold !== null && props.threshold !== undefined && props.limit > 0
    ? Math.min(1, Math.max(0, props.threshold / props.limit))
    : null,
)
</script>

<template>
  <div class="min-w-0">
    <div class="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <span class="font-mono text-xs text-fg-1 tabular-nums">{{ valueLabel }}</span>
      <span class="text-[0.6875rem] leading-3.5 text-fg-3">
        <template v-if="thresholdLabel">threshold {{ thresholdLabel }} · </template>
        limit {{ limitLabel }}
      </span>
    </div>
    <MemoryScoreBar :value="ratio" :threshold="tick" color="bg-fg-3" :label="label" />
  </div>
</template>
