<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue"
import { Check, Copy } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const props = withDefaults(
  defineProps<{
    id: string
    /** Example: "Agent ID", "Directive hash". */
    label?: string
    /** Hide the ID itself and render only the copy affordance. */
    iconOnly?: boolean
    /** Truncate very long IDs while keeping the full value in the tooltip. */
    truncate?: boolean
  }>(),
  { label: "ID", iconOnly: false, truncate: false },
)

const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

async function copy(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(props.id)
    copied.value = true
  } catch {
    copied.value = false
  }
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    copied.value = false
  }, 1_600)
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <span class="group/copy inline-flex min-w-0 items-center gap-1">
    <span
      v-if="!iconOnly"
      class="min-w-0 font-mono text-[0.6875rem] leading-4 text-fg-3 tabular-nums"
      :class="truncate ? 'truncate' : 'break-all'"
    >
      {{ id }}
    </span>
    <Tooltip :delay-duration="150">
      <TooltipTrigger as-child>
        <button
          type="button"
          class="inline-flex size-5 shrink-0 items-center justify-center rounded text-fg-3 opacity-60 transition-[opacity,color,background-color] hover:bg-raised hover:text-fg-1 group-hover/copy:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
          :aria-label="copied ? `${label} copied` : `Copy ${label} ${id}`"
          @click.stop.prevent="copy"
        >
          <Check v-if="copied" :size="11" :stroke-width="2.2" class="text-ok" aria-hidden="true" />
          <Copy v-else :size="11" :stroke-width="1.75" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" :side-offset="4" class="!text-xs">
        {{ copied ? "Copied" : `Copy ${label}` }}
      </TooltipContent>
    </Tooltip>
    <span class="sr-only" aria-live="polite">{{ copied ? `${label} copied` : "" }}</span>
  </span>
</template>
