<script setup lang="ts">
import { Lock } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

withDefaults(
  defineProps<{
    label: string
    icon?: unknown
    variant?: "primary" | "secondary" | "destructive"
    size?: "sm" | "md"
  }>(),
  { icon: undefined, variant: "secondary", size: "md" },
)

const READ_ONLY_TOOLTIP = "Read-only console. Requires a privileged write contract."
</script>

<template>
  <Tooltip :delay-duration="150">
    <TooltipTrigger as-child>
      <button
        type="button"
        disabled
        aria-disabled="true"
        :title="READ_ONLY_TOOLTIP"
        class="inline-flex shrink-0 cursor-not-allowed items-center gap-1.5 rounded-md border font-medium opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :class="[
          size === 'sm' ? 'h-7 px-2 text-[0.6875rem]' : 'h-8 px-2.5 text-xs',
          variant === 'primary' && 'border-line bg-raised text-fg-2',
          variant === 'secondary' && 'border-line-subtle bg-surface-1 text-fg-2',
          variant === 'destructive' && 'border-transparent bg-transparent text-crit',
        ]"
      >
        <component :is="icon" v-if="icon" :size="12" :stroke-width="1.75" aria-hidden="true" />
        {{ label }}
        <span class="sr-only">. {{ READ_ONLY_TOOLTIP }}</span>
        <Lock class="ml-0.5 opacity-70" :size="11" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </TooltipTrigger>
    <TooltipContent side="bottom" :side-offset="6" class="!max-w-64 !border !border-line !bg-overlay !text-xs !leading-4 !text-fg-2">
      {{ READ_ONLY_TOOLTIP }}
    </TooltipContent>
  </Tooltip>
</template>
