<script setup lang="ts">
import { computed } from "vue"
import { Archive, Check, CirclePause, CircleSlash, LoaderCircle } from "@lucide/vue"
import { agentStatusLabel, type AgentStatus } from "@/lib/agent-preview"

const props = withDefaults(
  defineProps<{
    status: AgentStatus
    /** Draining shows the remaining live sessions inline. */
    drainingCount?: number | null
  }>(),
  { drainingCount: null },
)

const config = computed(() => {
  switch (props.status) {
    case "active":
      return { icon: Check, tone: "border-line bg-raised text-fg-2", label: agentStatusLabel(props.status) }
    case "paused":
      return { icon: CirclePause, tone: "border-line bg-raised text-fg-2", label: agentStatusLabel(props.status) }
    case "draining":
      return {
        icon: LoaderCircle,
        tone: "border-transparent bg-transparent text-warn",
        label: `${agentStatusLabel(props.status)}${props.drainingCount ? ` (${props.drainingCount})` : ""}`,
      }
    case "suspended":
      return { icon: CircleSlash, tone: "border-transparent bg-transparent text-crit", label: agentStatusLabel(props.status) }
    default:
      return { icon: Archive, tone: "border-dashed border-line bg-transparent text-fg-3", label: agentStatusLabel(props.status) }
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
