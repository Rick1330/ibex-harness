<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string
    helper?: string | null
    /** Dense variant used by the session stat strip. */
    compact?: boolean
  }>(),
  { helper: null, compact: false },
)
</script>

<template>
  <div
    class="flex min-w-0 flex-col rounded-lg border border-line-subtle bg-surface"
    :class="compact ? 'gap-1 px-3 py-2' : 'gap-1.5 px-4 py-3'"
  >
    <p class="truncate text-xs leading-4 text-fg-3">{{ label }}</p>
    <p
      class="truncate font-mono font-semibold text-fg-1 tabular-nums"
      :class="compact ? 'text-lg leading-6 max-sm:text-[0.8125rem] max-sm:leading-5' : 'text-xl leading-7'"
    >{{ value }}</p>
    <p v-if="helper" class="truncate text-xs leading-4 text-fg-3">{{ helper }}</p>
    <div v-if="$slots.default" :class="compact ? 'mt-0.5' : 'mt-0.5'">
      <slot />
    </div>
  </div>
</template>
