<script setup lang="ts">
import { computed } from "vue"
import { Archive, Ban, Check, FilePenLine, RotateCcw, Timer } from "@lucide/vue"
import { DIRECTIVE_STATE_LABELS, type DirectiveState } from "@/lib/directive-preview"

const props = withDefaults(
  defineProps<{
    state: DirectiveState
    /** "Countered" marks a superseded version that once served traffic. */
    label?: string | null
  }>(),
  { label: null },
)

const config = computed(() => {
  switch (props.state) {
    case "live":
      return { icon: Check, tone: "border-transparent bg-transparent text-ok" }
    case "candidate":
      return { icon: Timer, tone: "border-transparent bg-transparent text-warn" }
    case "draft":
      return { icon: FilePenLine, tone: "border-dashed border-line bg-transparent text-fg-3" }
    case "rejected":
      return { icon: Ban, tone: "border-transparent bg-transparent text-crit" }
    case "rolled_back":
      return { icon: RotateCcw, tone: "border-transparent bg-transparent text-warn" }
    default:
      return { icon: Archive, tone: "border-line-subtle bg-raised text-fg-3" }
  }
})

const text = computed(() => props.label ?? DIRECTIVE_STATE_LABELS[props.state])
</script>

<template>
  <span
    class="inline-flex h-5.5 items-center gap-1.5 rounded-full border px-2 text-xs leading-none font-medium whitespace-nowrap"
    :class="config.tone"
    role="status"
    :aria-label="`Lifecycle: ${text}`"
  >
    <component :is="config.icon" :size="11" :stroke-width="2" aria-hidden="true" />
    {{ text }}
  </span>
</template>
