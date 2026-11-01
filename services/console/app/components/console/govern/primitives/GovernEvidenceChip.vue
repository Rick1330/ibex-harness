<script setup lang="ts">
import { computed } from "vue"
import { BadgeCheck, CircleDashed, CircleOff, ScanLine } from "@lucide/vue"
import { AUDIT_EVIDENCE_LABELS, type AuditEvidence } from "@/lib/audit-preview"

const props = defineProps<{ evidence: AuditEvidence }>()

const config = computed(() => {
  switch (props.evidence) {
    case "certified":
      return { icon: BadgeCheck, tone: "border-transparent bg-transparent text-ok" }
    case "sampled":
      return { icon: ScanLine, tone: "border-accent/30 bg-accent-tint text-accent" }
    case "partial":
      return { icon: CircleDashed, tone: "border-transparent bg-transparent text-warn" }
    default:
      return { icon: CircleOff, tone: "border-line-subtle bg-transparent text-fg-3" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ AUDIT_EVIDENCE_LABELS[evidence] }}
  </span>
</template>
