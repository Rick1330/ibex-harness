<script setup lang="ts">
import { computed } from "vue"
import { ArchiveX, Ban, Braces, Check, EyeOff, UserCheck } from "@lucide/vue"
import type { PolicyDecisionKind } from "@/lib/policy-preview"
import { POLICY_DECISION_LABELS } from "@/lib/policy-preview"

const props = defineProps<{ decision: PolicyDecisionKind }>()

const config = computed(() => {
  switch (props.decision) {
    case "blocked":
      return { icon: Ban, tone: "border-transparent bg-transparent text-crit" }
    case "approval":
      return { icon: UserCheck, tone: "border-transparent bg-transparent text-warn" }
    case "redacted":
      return { icon: EyeOff, tone: "border-memory/30 bg-memory-tint text-memory" }
    case "wrapped":
      return { icon: Braces, tone: "border-memory/30 bg-memory-tint text-memory" }
    case "tombstoned":
      return { icon: ArchiveX, tone: "border-line bg-raised text-fg-2" }
    default:
      return { icon: Check, tone: "border-transparent bg-transparent text-ok" }
  }
})

const label = computed(() => POLICY_DECISION_LABELS[props.decision])
</script>

<template>
  <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] font-medium whitespace-nowrap" :class="config.tone">
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ label }}
  </span>
</template>
