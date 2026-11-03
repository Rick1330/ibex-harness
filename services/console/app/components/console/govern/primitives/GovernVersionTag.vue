<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string | number
    tone?: "default" | "muted"
    link?: boolean
  }>(),
  { tone: "muted", link: false },
)
</script>

<template>
  <span
    class="inline-flex min-w-0 items-baseline gap-1 text-xs leading-4 whitespace-nowrap"
    :aria-label="`${label} ${value}`"
  >
    <span :class="tone === 'muted' ? 'text-fg-3' : 'text-fg-2'">{{ label }}</span>
    <span class="font-mono tabular-nums" :class="link ? 'text-fg-2 underline decoration-line-strong underline-offset-2' : 'text-fg-1'">
      {{ value }}
    </span>
  </span>
</template>
