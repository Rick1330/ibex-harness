<script setup lang="ts">
import { computed } from "vue"
import { ShieldCheck, TriangleAlert } from "@lucide/vue"
import { POLICY_MODE_LABELS, type PolicyMode } from "@/lib/policy-preview"

const props = defineProps<{ mode: PolicyMode }>()

const config = computed(() =>
  props.mode === "enforced"
    ? { icon: ShieldCheck, tone: "border-line bg-raised text-fg-2" }
    : { icon: TriangleAlert, tone: "border-transparent bg-transparent text-warn" },
)
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ POLICY_MODE_LABELS[mode] }}
  </span>
</template>
