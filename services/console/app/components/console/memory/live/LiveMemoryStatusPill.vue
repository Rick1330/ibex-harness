<script setup lang="ts">
import { computed } from "vue"
import { Archive, Check, CircleSlash, GitMerge, Trash2, TriangleAlert } from "@lucide/vue"
import type { MemoryStatus } from "~~/shared/operator/contracts"

const props = defineProps<{ status: MemoryStatus }>()

const config = computed(() => {
  switch (props.status) {
    case "active":
      return { icon: Check, tone: "border-line bg-raised text-ok", label: "Active" }
    case "quarantined":
      return { icon: TriangleAlert, tone: "border-transparent bg-transparent text-warn", label: "Quarantined" }
    case "deleted":
      return { icon: Trash2, tone: "border-transparent bg-transparent text-crit", label: "Deleted" }
    case "merged_into":
      return { icon: GitMerge, tone: "border-line bg-raised text-fg-3", label: "Merged" }
    case "superseded":
      return { icon: CircleSlash, tone: "border-line bg-raised text-fg-3", label: "Superseded" }
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
