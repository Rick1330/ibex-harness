<script setup lang="ts">
import { computed } from "vue"
import { Check, Circle, Clock, X } from "@lucide/vue"

const props = defineProps<{
  decision: "allow" | "deny" | "require_approval" | "not_evaluated"
}>()

const config = computed(() => {
  switch (props.decision) {
    case "allow":
      return { label: "Allowed", icon: Check, tone: "border-transparent bg-transparent text-ok" }
    case "deny":
      return { label: "Blocked", icon: X, tone: "border-transparent bg-transparent text-crit" }
    case "require_approval":
      return { label: "Needs approval", icon: Clock, tone: "border-transparent bg-transparent text-warn" }
    default:
      return { label: "Not evaluated", icon: Circle, tone: "border-line bg-raised text-fg-2" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[0.8125rem] leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    role="status"
  >
    <component :is="config.icon" :size="13" :stroke-width="2.2" aria-hidden="true" />
    {{ config.label }}
  </span>
</template>
