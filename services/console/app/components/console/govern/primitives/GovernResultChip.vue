<script setup lang="ts">
import { computed } from "vue"
import { Ban, Check, CircleX, RotateCw } from "@lucide/vue"
import { AUDIT_RESULT_LABELS, type AuditResult } from "@/lib/audit-preview"

const props = defineProps<{ result: AuditResult }>()

const config = computed(() => {
  switch (props.result) {
    case "applied":
      return { icon: Check, tone: "border-transparent bg-transparent text-ok" }
    case "rejected":
      return { icon: Ban, tone: "border-transparent bg-transparent text-crit" }
    case "retrying":
      return { icon: RotateCw, tone: "border-transparent bg-transparent text-warn" }
    default:
      return { icon: CircleX, tone: "border-transparent bg-transparent text-crit" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ AUDIT_RESULT_LABELS[result] }}
  </span>
</template>
