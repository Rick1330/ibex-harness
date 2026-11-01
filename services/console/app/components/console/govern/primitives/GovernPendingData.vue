<script setup lang="ts">
import { ChartNoAxesColumn } from "@lucide/vue"

withDefaults(
  defineProps<{
    title: string
    contract: string
    description?: string
  }>(),
  { description: undefined },
)
</script>

<template>
  <div
    class="flex max-h-40 min-h-20 flex-col justify-center gap-1 rounded-lg border border-dashed border-line-subtle bg-surface-1/40 px-4 py-3"
    role="status"
  >
    <p class="flex items-center gap-1.5 text-xs font-medium text-fg-2">
      <ChartNoAxesColumn :size="13" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
      {{ title }}
    </p>
    <p class="text-sm text-fg-1">Not reported yet</p>
    <p v-if="description" class="text-xs leading-4 text-fg-3">{{ description }}</p>
    <p class="font-mono text-[0.6875rem] leading-4 text-fg-3">
      Needs <code class="rounded bg-surface-2 px-1 py-0.5 text-fg-2">{{ contract }}</code>
    </p>
  </div>
</template>
