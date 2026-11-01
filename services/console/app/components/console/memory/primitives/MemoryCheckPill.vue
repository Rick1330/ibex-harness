<script setup lang="ts">
import { computed } from "vue"
import type { MemoryEvaluationResult } from "@/lib/memory-detail-preview"

const props = defineProps<{ result: MemoryEvaluationResult }>()

const config = computed(() => {
  switch (props.result) {
    case "no_finding":
      return { label: "No finding", tone: "border-transparent bg-transparent text-ok" }
    case "finding":
      return { label: "Finding", tone: "border-transparent bg-transparent text-warn" }
    default:
      return { label: "Not run", tone: "border-line bg-raised text-fg-3" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
    {{ config.label }}
  </span>
</template>
