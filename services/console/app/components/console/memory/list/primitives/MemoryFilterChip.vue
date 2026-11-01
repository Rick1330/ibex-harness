<script setup lang="ts">
import { X } from "@lucide/vue"

defineProps<{
  field: string
  value: string
}>()

const emit = defineEmits<{ remove: [] }>()
</script>

<template>
  <span class="inline-flex h-6 max-w-full items-center gap-1 rounded-full border border-line-subtle bg-surface-2 pl-2 pr-0.5 text-xs leading-none text-fg-2">
    <span class="truncate">
      <span class="text-fg-3">{{ field }}</span>
      <span class="text-fg-3" aria-hidden="true"> is </span>
      <span>{{ value }}</span>
    </span>
    <button
      type="button"
      class="inline-flex size-5 shrink-0 items-center justify-center rounded-full text-fg-3 transition-colors hover:bg-surface-1 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
      :aria-label="`Remove filter ${field} is ${value}`"
      @click.stop="emit('remove')"
    >
      <X :size="11" :stroke-width="2" aria-hidden="true" />
    </button>
  </span>
</template>
