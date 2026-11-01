<script setup lang="ts">
import { computed } from "vue"
import { Bot, Building2, MessagesSquare } from "@lucide/vue"
import { MEMORY_VISIBILITY_LABELS, type MemoryVisibility } from "@/lib/memory-preview"

const props = withDefaults(
  defineProps<{
    visibility: MemoryVisibility
    variant?: "row" | "chip"
  }>(),
  { variant: "row" },
)

const icon = computed(() => {
  if (props.visibility === "agent") return Bot
  if (props.visibility === "session") return MessagesSquare
  return Building2
})
const label = computed(() => MEMORY_VISIBILITY_LABELS[props.visibility])
</script>

<template>
  <span
    class="inline-flex items-center gap-1 whitespace-nowrap"
    :class="variant === 'chip' ? 'h-6 rounded-full border border-line-subtle bg-surface-2 px-2 text-xs text-fg-2' : 'text-xs text-fg-3'"
  >
    <component :is="icon" :size="11" :stroke-width="1.75" class="shrink-0" aria-hidden="true" />
    {{ label }}
  </span>
</template>
