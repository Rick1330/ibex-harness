<script setup lang="ts">
import { computed } from "vue"
import type { MemoryRetrievalUsage } from "@/lib/memory-detail-preview"

const props = withDefaults(
  defineProps<{
    usage: MemoryRetrievalUsage
    /** Memory pages describe context injection; session turns describe reply use. */
    labels?: "context" | "reply"
  }>(),
  { labels: "context" },
)

const config = computed(() => {
  const reply = props.labels === "reply"
  switch (props.usage) {
    case "injected":
      return {
        label: reply ? "Included in reply" : "Included in context",
        tone: "border-memory/40 bg-memory-tint text-memory",
      }
    case "retrieved_only":
      return {
        label: reply ? "Retrieved, not used" : "Retrieved, not included",
        tone: "border-line bg-raised text-fg-2",
      }
    default:
      return { label: "Below threshold", tone: "border-dashed border-line-strong text-fg-3" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    {{ config.label }}
  </span>
</template>
