<script setup lang="ts">
import { computed } from "vue"
import { ChevronDown } from "@lucide/vue"
import { MEMORY_PREVIEW_NOW } from "@/lib/memory-preview"

const props = defineProps<{
  total: number
  visible: number
  updatedRange: { from: string; to: string } | null
  hasMore: boolean
}>()

const emit = defineEmits<{ loadMore: [] }>()

const rangeLabel = computed(() => {
  if (!props.updatedRange) return "No updated timestamps recorded"
  const format = (value: string) =>
    new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(value))
  const from = format(props.updatedRange.from)
  const to = format(props.updatedRange.to)
  return from === to ? `Updated ${from}` : `Updated ${from} – ${to}`
})

const asOf = computed(
  () =>
    new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(MEMORY_PREVIEW_NOW)),
)
</script>

<template>
  <footer class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line-subtle py-2.5">
    <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] text-fg-3">
      <span class="font-mono text-fg-2 tabular-nums">{{ total }}</span>
      {{ total === 1 ? "memory" : "memories" }}
      <span class="text-fg-off" aria-hidden="true">·</span>
      <span>{{ rangeLabel }}</span>
      <span class="text-fg-off" aria-hidden="true">·</span>
      <span>Preview clock {{ asOf }}</span>
    </p>

    <div class="flex items-center gap-2">
      <p class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">
        {{ visible === 0 ? 0 : 1 }}–{{ visible }} of {{ total }}
      </p>
      <button
        v-if="hasMore"
        type="button"
        class="inline-flex h-7 items-center gap-1 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-[0.6875rem] font-medium text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        @click="emit('loadMore')"
      >
        Load more
        <ChevronDown :size="11" :stroke-width="1.9" aria-hidden="true" />
      </button>
    </div>
  </footer>
</template>
