<script setup lang="ts">
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

withDefaults(
  defineProps<{
    /** Defaults to the record-level "not recorded" wording. */
    reason?: string
  }>(),
  { reason: "Not recorded in this record" },
)
</script>

<template>
  <Tooltip :delay-duration="120">
    <TooltipTrigger as-child>
      <span
        tabindex="0"
        class="cursor-help rounded-sm border-b border-dotted border-line-strong text-fg-off focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :aria-label="reason"
      >
        —
      </span>
    </TooltipTrigger>
    <TooltipContent side="top" :side-offset="6" class="!text-xs">{{ reason }}</TooltipContent>
  </Tooltip>
</template>
