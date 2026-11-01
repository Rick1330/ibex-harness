<script setup lang="ts">
import { computed } from "vue"
import { BellOff, CircleAlert, CircleCheck, CircleDashed } from "@lucide/vue"
import { DRIFT_MONITOR_STATUS_LABELS } from "@/lib/govern-query"
import type { DriftMonitorStatus } from "@/lib/drift-preview"

const props = defineProps<{ status: DriftMonitorStatus }>()

const config = computed(() => {
  switch (props.status) {
    case "firing":
      return { icon: CircleAlert, tone: "border-transparent bg-transparent text-crit" }
    case "no_data":
      return { icon: CircleDashed, tone: "border-warn/40 bg-warn-tint text-warn" }
    case "muted":
      return { icon: BellOff, tone: "border-line-subtle bg-transparent text-fg-3" }
    default:
      return { icon: CircleCheck, tone: "border-transparent bg-transparent text-ok" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ DRIFT_MONITOR_STATUS_LABELS[status] }}
  </span>
</template>
