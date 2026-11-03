<script setup lang="ts">
import { computed } from "vue"
import { Archive, Check, CirclePause, CircleSlash } from "@lucide/vue"
import type { AgentStatus } from "~~/shared/operator/contracts"

const props = defineProps<{ status: AgentStatus }>()

const config = computed(() => {
  switch (props.status) {
    case "active":
      return { icon: Check, tone: "border-line bg-raised text-ok", label: "Active" }
    case "paused":
      return { icon: CirclePause, tone: "border-line bg-raised text-warn", label: "Paused" }
    case "suspended":
      return { icon: CircleSlash, tone: "border-transparent bg-transparent text-crit", label: "Suspended" }
    default:
      return { icon: Archive, tone: "border-dashed border-line bg-transparent text-fg-3", label: "Archived" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    role="status"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ config.label }}
  </span>
</template>
