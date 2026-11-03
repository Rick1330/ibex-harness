<script setup lang="ts">
import { computed } from "vue"
import { ArchiveX, Ban, Braces, EyeOff, ShieldCheck, UserCheck } from "@lucide/vue"
import { POLICY_EFFECT_LABELS, type PolicyEffect } from "@/lib/policy-preview"

const props = withDefaults(
  defineProps<{
    effect: PolicyEffect
    /** Show the condition code as a title instead of repeating it in the cell. */
    title?: string | null
  }>(),
  { title: null },
)

const config = computed(() => {
  switch (props.effect) {
    case "deny":
      return { icon: Ban, tone: "border-transparent bg-transparent text-crit" }
    case "require_approval":
      return { icon: UserCheck, tone: "border-transparent bg-transparent text-warn" }
    case "redact":
      return { icon: EyeOff, tone: "border-memory/30 bg-memory-tint text-memory" }
    case "wrap_as_data":
      return { icon: Braces, tone: "border-memory/30 bg-memory-tint text-memory" }
    case "tombstone":
      return { icon: ArchiveX, tone: "border-line bg-raised text-fg-2" }
    default:
      return { icon: ShieldCheck, tone: "border-transparent bg-transparent text-ok" }
  }
})
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    :title="title ?? undefined"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ POLICY_EFFECT_LABELS[effect] }}
  </span>
</template>
