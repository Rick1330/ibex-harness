<script setup lang="ts">
import { computed } from "vue"
import { Check, Circle, X } from "@lucide/vue"

const props = withDefaults(
  defineProps<{
    tone: "success" | "warning" | "destructive" | "neutral"
    label: string
    compact?: boolean
  }>(),
  { compact: false },
)

const config = computed(() => {
  switch (props.tone) {
    case "success":
      return { icon: Check, tone: "border-transparent bg-transparent text-ok" }
    case "warning":
      return { icon: Circle, tone: "border-transparent bg-transparent text-warn" }
    case "destructive":
      return { icon: X, tone: "border-transparent bg-transparent text-crit" }
    default:
      return { icon: Circle, tone: "border-line bg-raised text-fg-2" }
  }
})
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full border font-medium leading-none whitespace-nowrap"
    :class="[config.tone, compact ? 'h-5 px-1.5 text-[0.6875rem]' : 'h-5.5 px-2 text-xs']"
  >
    <component :is="config.icon" :size="10" :stroke-width="2.2" aria-hidden="true" />
    {{ label }}
  </span>
</template>
