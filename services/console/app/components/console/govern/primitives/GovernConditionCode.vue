<script setup lang="ts">
withDefaults(
  defineProps<{
    code: string
    /** Compact keeps the code on one line inside dense table cells. */
    compact?: boolean
  }>(),
  { compact: false },
)
</script>

<template>
  <code
    class="inline-block max-w-full rounded border border-line-subtle bg-surface-2 px-1.5 py-0.5 font-mono text-[0.6875rem] leading-4 text-fg-2"
    :class="compact ? 'truncate align-middle' : 'break-words whitespace-pre-wrap'"
  >{{ code }}</code>
</template>
