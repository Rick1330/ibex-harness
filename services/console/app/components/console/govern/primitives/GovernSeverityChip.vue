<script setup lang="ts">
import { computed } from "vue"
import { GOVERN_SEVERITY_LABELS, GOVERN_SEVERITY_MEANING, type GovernSeverity } from "@/lib/govern-severity"

const props = withDefaults(
  defineProps<{
    severity: GovernSeverity
    label?: string | null
  }>(),
  { label: null },
)

const config = computed(() => {
  switch (props.severity) {
    case "critical":
      return { dot: "bg-crit", tone: "border-transparent bg-transparent text-crit" }
    case "warning":
      return { dot: "bg-warn", tone: "border-transparent bg-transparent text-warn" }
    default:
      return { dot: "bg-line-strong", tone: "border-line bg-raised text-fg-2" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    :title="GOVERN_SEVERITY_MEANING[severity]"
  >
    <span class="size-1.5 rounded-full" :class="config.dot" aria-hidden="true" />
    {{ label ?? GOVERN_SEVERITY_LABELS[severity] }}
  </span>
</template>
