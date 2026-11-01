<script setup lang="ts">
import { computed } from "vue"
import { MEMORY_STATUS_LABELS, type MemoryStatus } from "@/lib/memory-preview"

const props = defineProps<{
  counts: Array<{ status: MemoryStatus; count: number }>
  total: number
  showLegend?: boolean
}>()

const segments = computed(() =>
  props.counts
    .filter((entry) => entry.count > 0)
    .map((entry) => ({
      ...entry,
      label: MEMORY_STATUS_LABELS[entry.status],
      width: (entry.count / Math.max(1, props.total)) * 100,
      color: `var(--ix-lifecycle-${entry.status})`,
    })),
)

const ariaLabel = computed(
  () => `Lifecycle: ${props.counts.map((entry) => `${entry.count} ${MEMORY_STATUS_LABELS[entry.status]}`).join(", ")}`,
)
</script>

<template>
  <div class="min-w-0">
    <div
      class="flex h-2 w-full overflow-hidden rounded-full bg-surface-2"
      role="img"
      :aria-label="ariaLabel"
    >
      <span
        v-for="segment in segments"
        :key="segment.status"
        class="h-full first:rounded-l-full last:rounded-r-full"
        :style="{ width: `${segment.width}%`, backgroundColor: segment.color }"
        :title="`${segment.label}: ${segment.count}`"
      />
    </div>
    <ul v-if="showLegend" class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] leading-4 text-fg-3">
      <li v-for="segment in segments" :key="segment.status" class="inline-flex items-center gap-1.5 whitespace-nowrap">
        <span class="size-1.5 rounded-full" :style="{ backgroundColor: segment.color }" aria-hidden="true" />
        <span>{{ segment.label }}</span>
        <span class="font-mono text-fg-2 tabular-nums">{{ segment.count }}</span>
      </li>
    </ul>
  </div>
</template>
