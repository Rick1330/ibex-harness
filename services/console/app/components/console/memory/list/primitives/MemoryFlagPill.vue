<script setup lang="ts">
import { computed } from "vue"
import {
  CalendarClock,
  CalendarX2,
  GitBranch,
  ScanEye,
  ShieldAlert,
} from "@lucide/vue"
import type { MemoryFlag, MemoryFlagKind } from "@/lib/memory-list"

const props = defineProps<{ flag: MemoryFlag }>()

const icon = computed(() => {
  const icons: Record<MemoryFlagKind, typeof CalendarClock> = {
    conflict: GitBranch,
    injection: ShieldAlert,
    pii: ScanEye,
    expiring: CalendarClock,
    expired: CalendarX2,
  }
  return icons[props.flag.kind]
})

const toneClass = computed(() => {
  if (props.flag.tone === "critical") return "text-crit"
  if (props.flag.tone === "warning") return "text-warn"
  return "text-fg-3"
})
</script>

<template>
  <span
    class="inline-flex max-w-full items-center gap-1 text-[0.625rem] leading-none font-medium whitespace-nowrap"
    :class="toneClass"
    :title="flag.title"
  >
    <component :is="icon" :size="11" :stroke-width="1.9" class="shrink-0" aria-hidden="true" />
    <span>{{ flag.label }}</span>
  </span>
</template>
