<script setup lang="ts">
import { Archive, Lock, Pin, Trash2, X } from "@lucide/vue"

defineProps<{ count: number }>()
const emit = defineEmits<{ clear: [] }>()
</script>

<template>
  <div
    class="pointer-events-none fixed inset-x-0 bottom-4 z-30 flex justify-center px-4"
    role="region"
    aria-label="Selection actions"
  >
    <div
      class="pointer-events-auto flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-1.5 rounded-full border border-line bg-overlay px-2 py-1.5 shadow-2xl"
    >
      <span class="flex items-center gap-1.5 pl-1 pr-0.5 text-xs text-fg-2">
        <span class="font-mono font-semibold text-fg-1 tabular-nums">{{ count }}</span>
        selected
      </span>
      <span class="mx-0.5 h-5 w-px bg-line-subtle" aria-hidden="true" />
      <button
        type="button"
        disabled
        class="inline-flex h-7 cursor-not-allowed items-center gap-1 rounded-full px-2 text-xs text-fg-off"
        aria-label="Pin selected memories unavailable"
        title="Read-only console. Requires a privileged write contract."
      >
        <Pin :size="12" :stroke-width="1.8" aria-hidden="true" />
        Pin
        <Lock :size="8" :stroke-width="2.4" aria-hidden="true" />
      </button>
      <button
        type="button"
        disabled
        class="inline-flex h-7 cursor-not-allowed items-center gap-1 rounded-full px-2 text-xs text-fg-off"
        aria-label="Archive selected memories unavailable"
        title="Read-only console. Requires a privileged write contract."
      >
        <Archive :size="12" :stroke-width="1.8" aria-hidden="true" />
        Archive
        <Lock :size="8" :stroke-width="2.4" aria-hidden="true" />
      </button>
      <button
        type="button"
        disabled
        class="inline-flex h-7 cursor-not-allowed items-center gap-1 rounded-full px-2 text-xs text-fg-off"
        aria-label="Delete selected memories unavailable"
        title="Read-only console. Requires a privileged write contract."
      >
        <Trash2 :size="12" :stroke-width="1.8" aria-hidden="true" />
        Delete
        <Lock :size="8" :stroke-width="2.4" aria-hidden="true" />
      </button>
      <span class="mx-0.5 h-5 w-px bg-line-subtle" aria-hidden="true" />
      <button
        type="button"
        class="inline-flex size-7 items-center justify-center rounded-full text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
        aria-label="Clear selection"
        @click="emit('clear')"
      >
        <X :size="13" :stroke-width="2" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
