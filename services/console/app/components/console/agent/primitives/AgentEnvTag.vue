<script setup lang="ts">
import { computed } from "vue"
import type { AgentEnv } from "@/lib/agent-preview"

const props = defineProps<{
  env: AgentEnv
}>()

/** Environment is deliberately neutral: it can never be mistaken for health. */
const tone = computed(() => {
  switch (props.env) {
    case "production":
      return "border-env-production/30 bg-env-production/10 text-env-production"
    case "staging":
      return "border-env-staging/30 bg-env-staging/10 text-env-staging"
    default:
      return "border-env-dev/30 bg-env-dev/10 text-env-dev"
  }
})
</script>

<template>
  <span
    class="inline-flex h-5 items-center rounded border px-1.5 font-mono text-[0.625rem] leading-none lowercase tracking-[0.01em]"
    :class="tone"
  >
    {{ env }}
  </span>
</template>
