<script setup lang="ts">
import { SearchX, Sparkles } from "@lucide/vue"
import type { MemoryFilterChip } from "@/lib/memory-list"
import MemoryFilterChipView from "./primitives/MemoryFilterChip.vue"

defineProps<{
  mode: "no-results" | "empty-workspace"
  chips?: MemoryFilterChip[]
  search?: string
}>()

const emit = defineEmits<{
  clear: []
  removeChip: [chip: MemoryFilterChip]
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 border-y border-line-subtle px-4 py-16 text-center">
    <span class="inline-flex size-10 items-center justify-center rounded-full bg-surface-2 text-fg-3">
      <SearchX v-if="mode === 'no-results'" :size="18" :stroke-width="1.7" aria-hidden="true" />
      <Sparkles v-else :size="18" :stroke-width="1.7" aria-hidden="true" />
    </span>

    <div>
      <p class="text-sm font-semibold text-fg-1">
        {{ mode === "no-results" ? "No memories match these filters" : "No memories yet" }}
      </p>
      <p class="mx-auto mt-1 max-w-md text-xs leading-5 text-fg-3">
        <template v-if="mode === 'no-results'">
          Filters are applied locally to the illustrative records in this browser. Remove a filter or clear the search to widen the result set.
        </template>
        <template v-else>
          This workspace has no memory records. Nothing is hidden and no empty-state data is simulated.
        </template>
      </p>
    </div>

    <div v-if="mode === 'no-results' && chips?.length" class="flex max-w-xl flex-wrap items-center justify-center gap-1.5">
      <MemoryFilterChipView
        v-for="chip in chips"
        :key="chip.key"
        :field="chip.field"
        :value="chip.value"
        @remove="emit('removeChip', chip)"
      />
      <MemoryFilterChipView v-if="search" field="Search" :value="`“${search}”`" @remove="emit('clear')" />
    </div>

    <button
      v-if="mode === 'no-results'"
      type="button"
      class="inline-flex h-8 items-center rounded-md border border-line-subtle bg-surface-1 px-3 text-xs font-medium text-fg-2 transition-colors hover:border-line hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      @click="emit('clear')"
    >
      Clear filters
    </button>
  </div>
</template>
