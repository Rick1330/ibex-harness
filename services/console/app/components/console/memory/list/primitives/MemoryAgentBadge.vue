<script setup lang="ts">
import { computed } from "vue"
import { memoryAgentIndex } from "@/lib/memory-list"

const props = withDefaults(
  defineProps<{
    name: string
    agentId: string
    showName?: boolean
  }>(),
  { showName: true },
)

const index = computed(() => memoryAgentIndex(props.agentId))
const initials = computed(() =>
  props.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join(""),
)
const style = computed(() => ({
  backgroundColor: `color-mix(in oklch, var(--ix-agent-${index.value}) 16%, transparent)`,
  color: "var(--ix-fg-1)",
}))
</script>

<template>
  <span class="inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap">
    <span
      class="inline-flex size-4.5 shrink-0 items-center justify-center rounded text-[0.5625rem] font-semibold leading-none"
      :style="style"
      aria-hidden="true"
    >
      {{ initials }}
    </span>
    <span v-if="showName" class="truncate text-xs text-fg-3">{{ name }}</span>
    <span v-else class="sr-only">{{ name }}</span>
  </span>
</template>
