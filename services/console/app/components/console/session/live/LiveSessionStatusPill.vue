<script setup lang="ts">
import { computed } from "vue"
import { Ban, Check, CircleSlash, TriangleAlert } from "@lucide/vue"
import type { SessionStatus } from "~~/shared/operator/contracts"

const props = defineProps<{ status: SessionStatus }>()

const config = computed(() => {
  switch (props.status) {
    case "active":
      return { icon: Check, tone: "border-line bg-raised text-ok", label: "Active" }
    case "completed":
      return { icon: CircleSlash, tone: "border-line bg-raised text-fg-3", label: "Completed" }
    case "abandoned":
      return { icon: Ban, tone: "border-dashed border-line bg-transparent text-fg-3", label: "Abandoned" }
    default:
      return { icon: TriangleAlert, tone: "border-transparent bg-transparent text-crit", label: "Error" }
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
