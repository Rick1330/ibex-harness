<script setup lang="ts">
import { computed } from "vue"
import { MEMORY_CATEGORY_LABELS, type MemoryCategory } from "@/lib/memory-preview"

const props = withDefaults(
  defineProps<{
    category: MemoryCategory
    variant?: "row" | "chip"
    extraLabels?: number
  }>(),
  { variant: "row", extraLabels: 0 },
)

const label = computed(() => MEMORY_CATEGORY_LABELS[props.category])
const color = computed(() => `var(--ix-cat-${props.category})`)
</script>

<template>
  <span
    class="inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap"
    :class="variant === 'chip' ? 'h-6 rounded-full border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2' : 'text-xs text-fg-3'"
  >
    <span class="size-1.5 shrink-0 rounded-full" :style="{ backgroundColor: color }" aria-hidden="true" />
    <span class="truncate">{{ label }}</span>
    <span v-if="extraLabels > 0" class="font-mono text-[0.625rem] text-fg-3">+{{ extraLabels }}</span>
  </span>
</template>
