<script setup lang="ts">
import { Info } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

defineProps<{
  /** Accessible label; the note itself goes in the slot. */
  label?: string
}>()
</script>

<template>
  <Tooltip :delay-duration="120">
    <TooltipTrigger as-child>
      <button
        type="button"
        class="inline-flex size-4 shrink-0 cursor-help items-center justify-center rounded-full text-fg-3 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-memory"
        :aria-label="label ?? 'About this field'"
        @click.stop.prevent
      >
        <Info :size="12" :stroke-width="1.75" aria-hidden="true" />
      </button>
    </TooltipTrigger>
    <TooltipContent side="top" :side-offset="6" class="!max-w-72 !border !border-line !bg-overlay !text-xs !leading-5 !text-fg-2">
      <slot />
    </TooltipContent>
  </Tooltip>
</template>
