<script setup lang="ts">
import { computed } from "vue"
import { BellOff, Check, Circle, Eye, RefreshCw } from "@lucide/vue"
import { DRIFT_STATE_LABELS, type DriftState } from "@/lib/drift-preview"

const props = defineProps<{ state: DriftState }>()

const config = computed(() => {
  switch (props.state) {
    case "open":
      return { icon: Circle, tone: "border-line-strong bg-surface-1 text-fg-1" }
    case "acknowledged":
      return { icon: Eye, tone: "border-accent/30 bg-accent-tint text-accent" }
    case "snoozed":
      return { icon: BellOff, tone: "border-line-subtle bg-transparent text-fg-3" }
    case "expected":
      return { icon: RefreshCw, tone: "border-memory/30 bg-memory-tint text-memory" }
    default:
      return { icon: Check, tone: "border-transparent bg-transparent text-ok" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    :aria-label="`Signal state: ${DRIFT_STATE_LABELS[state]}`"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ DRIFT_STATE_LABELS[state] }}
  </span>
</template>
