<script setup lang="ts">
import { AlertTriangle, RotateCcw } from "@lucide/vue"

defineProps<{ message: string }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div
    class="flex flex-col items-start gap-3 rounded-lg border border-crit/30 bg-crit-tint/40 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
    role="alert"
  >
    <div class="flex min-w-0 items-start gap-2.5">
      <AlertTriangle :size="16" :stroke-width="1.9" class="mt-0.5 shrink-0 text-crit" aria-hidden="true" />
      <div class="min-w-0">
        <p class="text-sm font-semibold text-fg-1">The memory list could not be rendered</p>
        <p class="mt-0.5 text-xs leading-5 text-fg-2">{{ message }}</p>
        <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">
          Nothing was written. Filters and view state are preserved in the URL.
        </p>
      </div>
    </div>
    <button
      type="button"
      class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-line bg-surface-1 px-3 text-xs font-medium text-fg-1 transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
      @click="emit('retry')"
    >
      <RotateCcw :size="13" :stroke-width="1.8" aria-hidden="true" />
      Retry
    </button>
  </div>
</template>
