<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string
    helper?: string | null
    tone?: "default" | "warning" | "critical" | "success"
    compact?: boolean
  }>(),
  { helper: null, tone: "default", compact: false },
)
</script>

<template>
  <div
    class="flex min-w-0 flex-col rounded-lg border border-line-subtle bg-surface"
    :class="compact ? 'gap-1 px-3 py-2' : 'gap-1 px-4 py-3'"
  >
    <p class="truncate text-xs leading-4 text-fg-3">{{ label }}</p>
    <p
      class="ix-kpi truncate"
      :class="[
        compact && 'text-xl leading-7 max-sm:text-lg',
        tone === 'warning' && 'text-warn',
        tone === 'critical' && 'text-crit',
        tone === 'success' && 'text-ok',
        tone === 'default' && 'text-fg-1',
      ]"
    >{{ value }}</p>
    <p v-if="helper" class="text-xs leading-4 text-fg-3" :class="compact ? 'truncate' : 'line-clamp-2'">{{ helper }}</p>
    <div v-if="$slots.default" class="mt-0.5">
      <slot />
    </div>
  </div>
</template>
