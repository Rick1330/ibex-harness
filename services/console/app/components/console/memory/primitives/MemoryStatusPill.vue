<script setup lang="ts">
import { computed } from "vue"
import { MEMORY_STATUS_LABELS, type MemoryStatus } from "@/lib/memory-preview"

const props = withDefaults(
  defineProps<{
    status: MemoryStatus
    /** Compact label for dense list rows; the detail view keeps the review prompt. */
    compact?: boolean
  }>(),
  { compact: false },
)

const tone = computed(() => {
  switch (props.status) {
    case "active":
      return "text-ok"
    case "quarantined":
      return "text-warn"
    case "deleted":
      return "text-crit"
    case "archived":
    case "superseded":
    case "merged_into":
      return "text-fg-3"
    default:
      return "text-fg-3"
  }
})

const label = computed(() => {
  if (props.status === "quarantined" && !props.compact) return "Quarantined · human review required"
  return MEMORY_STATUS_LABELS[props.status]
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 text-[0.6875rem] font-medium leading-none whitespace-nowrap"
    :class="tone"
  >
    <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
    {{ label }}
  </span>
</template>
