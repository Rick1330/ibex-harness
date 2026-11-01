<script setup lang="ts">
import { computed } from "vue"
import { TriangleAlert } from "@lucide/vue"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"

const props = withDefaults(
  defineProps<{
    value: string
    /** Above-threshold values get warning colour + arrow + the band hint. */
    over?: boolean
    /** e.g. "Band: ≤ 2.0%". Shown in the InfoHint and on hover. */
    threshold?: string
    /** Destructive is reserved for failed/blocked, not merely above band. */
    tone?: "default" | "warning" | "destructive"
    align?: "left" | "right"
  }>(),
  { over: false, threshold: undefined, tone: "default", align: "right" },
)

const resolvedTone = computed(() => {
  if (props.tone === "destructive") return "text-crit"
  if (props.tone === "warning" || props.over) return "text-warn"
  return "text-fg-1"
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1 font-mono text-xs tabular-nums"
    :class="[resolvedTone, align === 'right' && 'justify-end']"
    :title="threshold"
  >
    {{ value }}
    <TriangleAlert v-if="over || tone === 'warning' || tone === 'destructive'" :size="11" :stroke-width="2.2" aria-hidden="true" />
    <span v-if="over || tone === 'warning' || tone === 'destructive'" class="sr-only">
      above {{ threshold ?? "the recorded band" }}
    </span>
    <MemoryInfoHint v-if="threshold" :label="`Threshold: ${threshold}`">
      {{ threshold }}
    </MemoryInfoHint>
  </span>
</template>
