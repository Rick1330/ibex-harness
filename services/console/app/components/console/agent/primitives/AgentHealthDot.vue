<script setup lang="ts">
import { computed } from "vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { agentHealthLabel, type AgentHealthState, type HealthReason } from "@/lib/agent-preview"

const props = withDefaults(
  defineProps<{
    health: AgentHealthState
    /** Reasons rendered in the tooltip so the dot always explains itself. */
    reasons?: HealthReason[]
    /** Hide the word for dense cells that carry their own label. */
    dotOnly?: boolean
    size?: "sm" | "md"
  }>(),
  { reasons: () => [], dotOnly: false, size: "md" },
)

const dotClass = computed(() => {
  switch (props.health) {
    case "healthy":
      return "bg-ok"
    case "attention":
      return "bg-warn"
    case "failing":
      return "bg-crit"
    case "paused":
      return "border border-fg-off bg-transparent"
    case "archived":
      return "border border-dashed border-fg-off bg-transparent"
    default:
      return "border border-fg-3 bg-transparent"
  }
})

const wordClass = computed(() => {
  switch (props.health) {
    case "healthy":
      return "text-fg-1"
    case "attention":
      return "text-warn"
    case "failing":
      return "text-crit"
    default:
      return "text-fg-3"
  }
})

const label = computed(() => agentHealthLabel(props.health))
</script>

<template>
  <Tooltip v-if="reasons.length" :delay-duration="150">
    <TooltipTrigger as-child>
      <span
        tabindex="0"
        class="inline-flex items-center gap-1.5 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :aria-label="`${label}. ${reasons.length} ${reasons.length === 1 ? 'reason' : 'reasons'}.`"
      >
        <span class="shrink-0 rounded-full" :class="[dotClass, size === 'sm' ? 'size-1.5' : 'size-2']" aria-hidden="true" />
        <span v-if="!dotOnly" class="text-xs font-medium whitespace-nowrap" :class="wordClass">{{ label }}</span>
      </span>
    </TooltipTrigger>
    <TooltipContent side="top" :side-offset="6" class="!max-w-80 !border !border-line !bg-overlay !p-3 !text-xs !text-fg-2">
      <p class="mb-1.5 text-xs font-medium text-fg-1">{{ label }}</p>
      <ul class="space-y-1">
        <li v-for="reason in reasons" :key="reason.code" class="flex items-start gap-1.5 leading-4">
          <span
            class="mt-1 size-1.5 shrink-0 rounded-full"
            :class="reason.severity === 'critical' ? 'bg-crit' : reason.severity === 'warning' ? 'bg-warn' : 'bg-fg-3'"
            aria-hidden="true"
          />
          <span>
            {{ reason.title }}
            <span class="font-mono text-fg-3 tabular-nums">({{ reason.value }} · {{ reason.threshold }})</span>
          </span>
        </li>
      </ul>
    </TooltipContent>
  </Tooltip>
  <span v-else class="inline-flex items-center gap-1.5" :aria-label="label">
    <span class="shrink-0 rounded-full" :class="[dotClass, size === 'sm' ? 'size-1.5' : 'size-2']" aria-hidden="true" />
    <span v-if="!dotOnly" class="text-xs font-medium whitespace-nowrap" :class="wordClass">{{ label }}</span>
  </span>
</template>
