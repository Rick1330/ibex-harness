<script setup lang="ts">
import { Info, Lock, TriangleAlert } from "@lucide/vue"

withDefaults(
  defineProps<{
    tone?: "info" | "warning" | "lock"
    title?: string | null
  }>(),
  { tone: "info", title: null },
)
</script>

<template>
  <div
    class="flex items-start gap-2 rounded-lg border px-3 py-2 text-xs leading-5"
    :class="
      tone === 'warning'
        ? 'border-warn/30 bg-warn-tint/60 text-warn'
        : tone === 'lock'
          ? 'border-line-subtle bg-surface-2 text-fg-3'
          : 'border-line-subtle bg-surface-2 text-fg-2'
    "
    role="note"
  >
    <Lock v-if="tone === 'lock'" :size="13" :stroke-width="1.8" class="mt-0.5 shrink-0" aria-hidden="true" />
    <TriangleAlert v-else-if="tone === 'warning'" :size="13" :stroke-width="1.8" class="mt-0.5 shrink-0" aria-hidden="true" />
    <Info v-else :size="13" :stroke-width="1.8" class="mt-0.5 shrink-0 text-fg-3" aria-hidden="true" />
    <p class="min-w-0">
      <span v-if="title" class="mr-1 font-medium">{{ title }}</span>
      <slot />
    </p>
  </div>
</template>
