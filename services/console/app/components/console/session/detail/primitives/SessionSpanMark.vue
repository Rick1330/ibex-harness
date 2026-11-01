<script setup lang="ts">
import { computed } from "vue"
import { Braces, Database, ShieldCheck, Sparkles, Wrench } from "@lucide/vue"
import type { SessionSpanKind } from "@/lib/session-preview"

const props = withDefaults(
  defineProps<{
    kind: SessionSpanKind
    size?: number
  }>(),
  { size: 13 },
)

const config = computed(() => {
  switch (props.kind) {
    case "retrieval":
      return { icon: Database, label: "Retrieval" }
    case "tool":
      return { icon: Wrench, label: "Tool" }
    case "llm":
      return { icon: Sparkles, label: "LLM" }
    case "policy":
      return { icon: ShieldCheck, label: "Policy" }
    default:
      return { icon: Braces, label: "Internal" }
  }
})
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center"
    :style="{ color: `var(--ix-span-${kind})` }"
    :title="config.label"
  >
    <component :is="config.icon" :size="size" :stroke-width="1.9" aria-hidden="true" />
    <span class="sr-only">{{ config.label }} span</span>
  </span>
</template>
